# Software Supply Chain, Container Images, and Trusted Deployment Sources

A cloud application is built from more than just the development team's source code. It also depends on third-party libraries, package managers, base images, compilers, build runners, CI/CD workflows, artifact registries, deployment controllers, IaC modules, and various automation services. Every link can introduce code or configuration into production. If a dependency is hijacked, a CI token is stolen, an image is substituted, or a pipeline pulls an artifact of unknown origin, the system may deploy modified software even while the main repository remains clean.

That is the risk of the **software supply chain**. Security is not merely scanning source code for vulnerabilities—it requires proving which source, workflow, dependencies, and tools produced an artifact; protecting artifacts from tampering; verifying signatures and provenance before deployment; and constraining build/deploy system privileges. For containers, this requires immutable image digests, trusted base images, SBOMs, provenance attestations, signature verification, and runtime policies.

This lesson belongs to the **Security Architecture** chapter of the **CLOUD_ARCHITECTURE** module. The focus is building a trusted path from source to production while balancing reliability, security, scalability, cost, and operations using Well-Architected thinking.

## 1. Learning Objectives

After this lesson, learners can:

1. Describe the components and trust boundaries across the software supply chain.
2. Distinguish source integrity, build integrity, artifact integrity, provenance, and deployment authorization.
3. Design CI/CD with least privilege, isolated runners, short-lived secrets, and environment-based approvals.
4. Manage dependencies, packages, base images, and container images by pinned version/digest.
5. Explain SBOMs, vulnerability scanning, provenance attestations, and artifact signing.
6. Establish admission policies permitting only workloads using compliant images/artifacts.
7. Protect IaC, manifests, and deployment configurations from unauthorized changes.
8. Handle revoked images, compromised dependencies, compromised signing keys, and build pipeline incidents.
9. Measure coverage, remediation time, and supply chain control effectiveness.

## 2. What Is the Software Supply Chain?

### 2.1. Links in a Release

A typical flow:

~~~mermaid
flowchart LR
    SRC[Source repository] --> REVIEW[Review and protected branch]
    REVIEW --> CI[CI workflow]
    CI --> DEPS[Dependencies and toolchain]
    DEPS --> BUILD[Build and test]
    BUILD --> SBOM[SBOM and provenance]
    SBOM --> SIGN[Sign artifact]
    SIGN --> REG[Artifact registry]
    REG --> VERIFY[Verify signature and policy]
    VERIFY --> DEPLOY[CD / deployment controller]
    DEPLOY --> RUN[Production runtime]
    RUN --> MON[Monitor and respond]
~~~

Each step takes inputs and produces outputs that can influence subsequent steps. For instance, a source commit may be reviewed while the build workflow executes a compromised third-party action, producing a trojanized image. Or the build may be clean while the registry permits tag overwrites, causing deployment to pull a different image than the one tested.

### 2.2. Assets to Protect

- Source code, branches, tags, commits, and review metadata.
- Packages/dependencies, package registries, and lockfiles.
- Compilers, build tools, base images, build scripts, and runners.
- CI workflows, reusable actions, plugins, and credentials.
- Binaries, packages, container images, Helm charts, and IaC modules.
- SBOMs, provenance, test results, vulnerability reports, and signatures.
- Artifact registries, signing services, keys, and identities.
- Deployment manifests, GitOps repositories, admission policies, and cluster credentials.
- Runtime images, nodes, workload identities, and secrets used by workloads.

### 2.3. Threat Model by Boundary

| Component | Risk | Example Consequence |
|---|---|---|
| Source repository | Compromised account/branch, bypassed review | Malicious code merged |
| Dependency | Typosquatting package or compromised maintainer | Malicious code executes at build or runtime |
| Build workflow | Workflow injection, unpinned actions, compromised runner | Artifact tampered with |
| Secret | Long-lived token leaked in logs or runners | Attackers publish images/deploy |
| Registry | Tag overwritten, overly broad push rights | Production image replaced |
| Provenance | Forged or unchecked attestation | Unverified-origin artifact trusted |
| Deployment | Compromised manifest/cluster credentials | Unauthorized workload runs |
| Runtime | Exploitable image, overly broad container privileges | Lateral movement and data exfiltration |

## 3. Principles for Building a Trusted Supply Chain

### 3.1. Verify Origin Before Trusting

An artifact is not trustworthy merely because it sits in an internal registry. You must know:

- Which repository and commit produced it.
- Which workflow and identity built it.
- Which builders/toolchains and dependencies were used.
- Whether it was tested/scanned per policy.
- Whether SBOM and provenance are bound to the exact digest.
- Whether it carries a valid signature from an authorized identity.
- Which environments it was approved for.

### 3.2. Protect Every Step

Defense in depth applies from source to runtime:

- Protect repositories and branches.
- Pin dependencies and build actions.
- Use isolated, ephemeral runners wherever possible.
- Do not grant production credentials to routine build jobs.
- Sign artifacts and store evidence.
- Verify prior to deployment and at the admission layer.
- Run at runtime as non-root with read-only filesystems and least privilege.
- Track changes and maintain artifact revocation capability.

### 3.3. Fail Closed at Critical Boundaries

If production policy requires an image signed by an approved identity, the system should not silently bypass verification failures because a registry is slow or an attestation is missing. A separate break-glass path with time limits, approvers, and auditing can exist; never make exceptions the default.

### 3.4. Separate Build and Deploy

The build system produces artifacts. The deployment system decides which artifact goes to which environment. Separating these privileges reduces the chance that a malicious dependency inside a build job acquires production deployment rights. Artifacts move via a controlled registry or channel along with their digest and evidence.

## 4. Protecting Source Repositories

### 4.1. Branch and Review Protection

Critical repositories should enforce:

- Protected default/release branches.
- Mandatory pull requests instead of direct pushes.
- Required reviews and code owners for sensitive paths.
- Required status checks and policy tests.
- Signed commits/tags where supported by the workflow.
- Restricted permissions to create/modify releases and repository settings.
- Auditing of branch protection changes, webhooks, and tokens.

Not every project needs multiple approval layers. Control rigor should match criticality, blast radius, and team size.

### 4.2. CODEOWNERS and Workflow Controls

Pipeline, deployment, IaC, policy, and build script files wield elevated power. Changes to these files can expose secrets or bypass checks. Require code owner reviews on sensitive paths; test workflow changes in environments without production credentials before merging.

### 4.3. Repository Tokens

Scope tokens to specific repositories, permissions, and lifetimes. Avoid long-lived personal tokens for automation; prefer workload identity/OIDC federation or least-privilege app integrations. Revoke unused tokens, audit access events, and detect committed secrets.

## 5. Dependency and Package Management

### 5.1. Direct and Transitive Dependencies

Applications have direct dependencies declared by the team and transitive dependencies pulled in indirectly. A small package deep in the graph can still execute during build or runtime. SBOMs and scanners must inspect the entire dependency tree, not just top-level manifest files.

### 5.2. Lockfiles and Reproducible Versions

Lockfiles record resolved dependency versions and often include integrity hashes. Production builds should install reproducibly from lockfiles, avoiding silent dependency upgrades between builds. Updates should be intentional, reviewed, and tested.

~~~text
Package manifest:
  declares required version ranges

Lockfile:
  records exact resolved versions
  records integrity/hashes if supported by the package manager

CI:
  installs dependencies from the lockfile
  does not unexpectedly resolve new versions
~~~

Lockfiles reduce nondeterminism but do not prove a package is safe. A malicious package can still be pinned to an exact version.

### 5.3. Package Confusion and Typosquatting

Common risks:

- Package names closely resembling popular packages.
- Dependency confusion between internal packages and public registries.
- Spoofed repositories or compromised maintainer accounts.
- Packages with install scripts executing arbitrary commands.
- Typosquatting or abandoned, unmaintained packages.

Countermeasures:

- Use namespaces/private registries for internal packages.
- Configure explicit registry scoping.
- Allowlist package sources when needed.
- Inspect maintainers, repositories, release history, and install script behavior.
- Enforce lockfiles, integrity verification, and dependency reviews.
- Monitor packages flagged as malicious or yanked/revoked.

### 5.4. Dependency Update Policies

Avoid both extremes: freezing dependencies forever or auto-deploying every package update straight to production. Weigh:

- Dependency criticality.
- Vulnerability severity and exploitability.
- Release cadence and support lifecycle.
- API/schema compatibility.
- Test coverage and rollback paths.
- Security advisory remediation deadlines.

Automated pull requests for dependency updates can be helpful; automatically merging and deploying updates without policies and tests is not safe.

### 5.5. Secrets During Dependency Installation

Package install scripts can execute inside build runners. Never expose production secrets during package download/installation steps. Restrict network egress, token scopes, and registry write access; isolate untrusted build jobs (such as pull requests from forks) from release jobs holding signing/publishing rights.

## 6. Securing CI/CD and Build Environments

### 6.1. Pipelines Are Security Assets

CI/CD can read source, packages, and secrets, sign artifacts, and deploy to production. If a pipeline is compromised, attackers can bypass many application-layer defenses. Protect:

- Workflow definitions and reusable pipelines.
- Runner images, runner hosts, and caches.
- Plugins/actions and their versions.
- Secrets/identities issued per job.
- Network egress and API permissions.
- Artifact outputs and logs.
- Approvals and deployment environments.

### 6.2. Isolated Runners

Prefer ephemeral runners or runners wiped after each job. Never share workspaces, credentials, or Docker daemons across jobs of different trust levels. Jobs running code from forks/untrusted pull requests need isolated sandboxes and zero release secrets.

### 6.3. Pinning Actions and Toolchains

Referencing actions/plugins by mutable tags risks receiving altered code. For sensitive pipelines, pin immutable commit digests/hashes where supported, review updates, and document trusted sources. Pinning does not remove vulnerabilities already inside a pinned version; controlled updates are still needed.

### 6.4. OIDC and Short-Lived Credentials

Instead of storing long-lived cloud access keys in CI secrets, use OIDC federation:

1. The CI workload receives an identity token with audience and claims.
2. Cloud IAM validates issuer, subject, repository, branch/environment, and audience.
3. If policy matches, short-lived credentials with a scoped role are issued.
4. Credentials automatically expire after the job/session.

Policies must bind the exact repository and workflow. If a trust policy checks only a broad issuer without constraining subject/audience, unintended workflows can claim the role.

### 6.5. Per-Job Least Privilege

Do not grant full permissions to the entire pipeline. For example:

| Job | Required Permissions | Permissions to Withhold |
|---|---|---|
| PR lint/test | Read source, download dependencies | Publish releases, deploy production |
| Build candidate | Read source/dependencies, write staging artifacts | Modify IAM or read production secrets |
| Sign release | Read approved artifacts, use signing identity | Modify source or self-approve changes |
| Deploy staging | Read artifacts, update staging | Write to production |
| Deploy production | Read signed artifacts, narrow deploy rights | Publish/modify artifacts |

### 6.6. Build Reproducibility and Hermetic Builds

Reproducible builds aim to produce identical artifacts (byte-for-byte or to a verifiable degree) given the same source, dependencies, and environment. Hermetic builds restrict inputs so builds cannot fetch arbitrary data from the network while running.

Benefits:

- Easier to trace where artifact differences originated.
- Reduces unexpected reliance on external services.
- Enables independent build verification.
- Simplifies investigation when an artifact is suspect.

The trade-off is greater complexity in managing caches, toolchains, dependency mirrors, and build environments. Not every system today needs strict bit-for-bit reproducibility; choose the level matching your risk.

## 7. Trusted Container Images

### 7.1. Images Are Immutable Artifacts by Digest

Container images are often referenced by tags like `release-2026-11` or `latest`, yet tags can be overwritten. A digest identifies exact image contents:

~~~text
registry.example.com/booking/api@sha256:<image-digest>
~~~

Production manifests should reference tested/approved digests. Tags remain useful for humans, but should not be the sole identifier of what gets deployed.

### 7.2. Choosing Base Images

Select base images from official sources or controlled registries, pin by digest, update for security advisories, and keep components minimal. Smaller images usually reduce attack surface and pull times, though they do not replace scanning or runtime controls.

Prefer:

- Base images with clear update schedules and support windows.
- Distroless/minimal images when compatible with the workload.
- Omitting unnecessary compilers, package managers, or debug utilities from runtime images.
- Avoiding arbitrary package upgrades at container startup.
- Rebuilding systematically when base images receive CVEs.

### 7.3. Multi-Stage Builds

~~~dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
USER 10001:10001
EXPOSE 8080
CMD ["node", "dist/server.js"]
~~~

This is an illustrative example; in production, pin base images by digest, consider copying only production dependencies, and verify file permissions, health checks, and build metadata. Never place `.env` files, private keys, tokens, or environment configs into image layers.

### 7.4. Never Leave Secrets in Image Layers

Deleting a secret in a later layer does not remove it from earlier layers. Use builder secret mounts or fetch secrets at runtime from a secret manager via workload identity. Audit the build context and `.dockerignore` to avoid copying sensitive local files.

### 7.5. Container Runtime Hardening

- Run as non-root with explicit UID/GID.
- Use a read-only root filesystem where the application permits.
- Drop unnecessary Linux capabilities.
- Never use privileged mode.
- Enforce CPU, memory, PID, and ephemeral storage limits.
- Apply platform-appropriate seccomp/AppArmor/SELinux profiles.
- Never mount the Docker socket or arbitrary host paths.
- Apply network policies and least-privilege workload identities.
- Run only images scanned and verified per policy.

## 8. SBOM: Knowing What Software Contains

### 8.1. What Is an SBOM?

A Software Bill of Materials (SBOM) inventories the components inside a piece of software or artifact. It can record:

- Package/component names and versions.
- Package URLs (PURLs), suppliers, and licenses.
- Dependency relationships.
- Hashes or identifiers where supported by the format.
- Metadata about the SBOM generator tool and timestamp.

Common formats include SPDX and CycloneDX. Choose a format compatible with your tooling, partners, and compliance requirements.

### 8.2. An SBOM Is Not a Security Certification

An SBOM tells you what software contains, not that every component is safe. Its value depends on completeness, accuracy, binding to the exact artifact digest, and updating when dependencies change.

An SBOM generated from source that misses the final image may omit OS packages or runtime layers. Generate/reconcile SBOMs during artifact build and bind them to the specific digest.

### 8.3. Using SBOMs When New Vulnerabilities Emerge

When a CVE is disclosed for a dependency:

1. Identify affected packages, versions, and scope.
2. Query SBOMs to locate artifacts containing that component.
3. Identify affected image digests and running workloads.
4. Prioritize by exposure, exploitability, and criticality.
5. Rebuild and release patched artifacts.
6. Monitor rollouts and verify old images are no longer running.

Without an SBOM, incident responders often must re-scan many artifacts or guess from current lockfiles while old vulnerable images remain running.

## 9. Provenance and Attestation

### 9.1. What Is Provenance?

Provenance describes how and where an artifact was produced. It can capture:

- Source repository and commit.
- Builder/workflow identity.
- Build invocation and meaningful parameters.
- Dependency/material references.
- Timestamp and build type.
- Subject artifact and digest.

Provenance lets consumers verify the link between source, build process, and output. It does not prove source is bug-free; it proves origin and process to the level of declared evidence.

### 9.2. Attestation

An attestation is a structured statement about a subject (such as an image digest) issued by an identity. It can carry provenance, SBOMs, test results, or policy evidence. Attestations need:

- A subject digest precisely identifying the artifact.
- A predicate/type specifying the kind of claim.
- A trusted issuer/builder identity.
- A verified signature or integrity mechanism.
- Timestamp and context.
- A consumer-side verification policy.

### 9.3. Do Not Trust Metadata Just Because It Travels with an Image

Attackers can forge SBOM/provenance files if there is no signature or trusted issuer. Consumers must cryptographically verify attestations and evaluate their policy contents—never merely check that a file exists.

## 10. Signing and Verifying Artifacts

### 10.1. Why Sign?

Digital signatures bind an artifact/digest to an authorized signing identity. During verification, the system checks:

- Has the artifact been modified since signing?
- Which identity/key produced the signature?
- Is the key/certificate trusted and still valid?
- Does the signature match the subject digest?
- Is that identity authorized to release for that artifact type and environment?

### 10.2. Cosign and Container Signing (Example)

A reference workflow using Cosign:

~~~bash
# Sign an image digest with an approved signing identity
cosign sign registry.example.com/booking/api@sha256:IMAGE_DIGEST

# Verify the signature against the expected identity/issuer
cosign verify \
  --certificate-identity "https://example.com/ci/release" \
  --certificate-oidc-issuer "https://token.actions.example" \
  registry.example.com/booking/api@sha256:IMAGE_DIGEST
~~~

These are illustrative commands; identities, issuers, keyless/key-based modes, and tool versions must match your real environment. Passing `verify` alone is insufficient if policy also requires checking provenance, SBOMs, or vulnerability thresholds.

### 10.3. Signing Key Management

Signing keys are critical assets. Protect them with KMS/HSM or keyless signing backed by proper identity federation; restrict signing rights; audit every signature; rotate per policy; and prepare revocation/identity-denial procedures after compromise.

Never allow an untrusted build job that modifies source to also hold production release signing rights. Separate signing until after artifacts are tested and approved.

### 10.4. Keyless Signing

Some systems use short-lived OIDC identities instead of holding long-lived private signing keys. A signing service issues certificates bound to workload identity, and transparency logs can supply additional evidence. Even though keyless signing reduces long-lived private key risk, policies must still verify issuer, subject, audience, and workflow identity. A compromised workflow granted a valid identity can still sign malicious artifacts if approval conditions are weak.

## 11. Vulnerability Scanning and Policy Triage

### 11.1. Scanning Across Layers

| Layer | Scope | Typical Tools/Controls |
|---|---|---|
| Source | SAST, secret scanning, IaC scanning | Code analysis, credential detection, risky config checks |
| Dependency | SCA and license review | Package graph analysis and advisories |
| Build | Toolchain, workflows, runners | Pin actions, runner image scanning, workflow review |
| Image | OS packages, language libraries, malware | Container scanners, SBOMs |
| Artifact | Provenance, signatures, integrity | Attestation verification |
| Deployment | Manifests, policies, and permissions | IaC/Kubernetes policy validation |
| Runtime | Behavior, processes, network, files | Runtime detection and workload policies |

### 11.2. Severity Is Not the Whole Decision

Never rely solely on CVSS scores. Consider:

- Is there a known or actively exploited exploit?
- Is the vulnerable package actually present and loaded?
- Is the attack path reachable from networks/users?
- Is the workload privileged or handling sensitive data?
- Are there mitigations or unused code paths?
- What are remediation SLAs based on criticality and contracts?

### 11.3. Example Policy

A production policy might require:

- Zero critical vulnerabilities without an approved exception.
- High-severity vulnerabilities have remediation deadlines and owners.
- Zero secrets detected inside the image.
- SBOM and provenance bound to the exact digest.
- Image signed by an authorized release identity.
- Base image not past end-of-life.
- Exceptions include justification, scope, expiration, and approver.

Concrete thresholds must align with risk appetite and tooling. Blocking every CVE regardless of exploitability or fix availability can stall pipelines; ignoring findings due to alert fatigue renders policy meaningless.

## 12. Artifact Registries and Cross-Environment Promotion

### 12.1. The Registry Is a Trust Boundary

Registries should support:

- Private repositories and authentication.
- Separate pull/push permissions by team, project, and environment.
- Immutable tags or overwrite-prevention policies.
- Digests, retention, replication, and auditing.
- Vulnerability scanning/integrations.
- Artifact quarantine and deletion/deny policies.

Do not grant production image push access to every developer or every CI workflow.

### 12.2. Build Once, Promote the Same Digest

A strong practice is building an artifact once, then promoting that exact digest through staging, pre-production, and production:

~~~mermaid
flowchart LR
    BUILD[Build candidate] --> TEST[Test and scan]
    TEST --> SIGN[Sign and attest]
    SIGN --> REG[Immutable registry digest]
    REG --> STAGE[Deploy staging]
    STAGE --> APPROVE[Approval / policy gate]
    APPROVE --> PROD[Deploy same digest to production]
~~~

Do not rebuild separately for production if you want proof that the tested artifact is the deployed artifact. Environment configuration may vary, while the image digest stays identical.

### 12.3. Promotion Manifests

Deployment manifests should record:

- Image digest.
- Release/source commit.
- SBOM and provenance references.
- Signature verification result.
- Target environment/region.
- Configuration version.
- Approval/change record.

Manifests also require version control and integrity checks to prevent unauthorized digest or target edits.

## 13. Admission Control and Pre-Runtime Verification

### 13.1. Admission Is the Final Gate Before Workloads Run

An admission controller/policy engine can validate workload creation or update requests:

- Is the registry in the allowlist?
- Is the image referenced by digest?
- Are the signature and issuer identity valid?
- Does the provenance subject match the digest?
- Do SBOM and scan evidence satisfy policy?
- Is the namespace/service account allowed to run this image?
- Does the workload violate runtime policies such as privileged/root/hostPath?

### 13.2. Conceptual Policy Example

~~~yaml
apiVersion: policy.example/v1
kind: ImageTrustPolicy
metadata:
  name: production-image-trust
spec:
  namespaces:
    - production
  requireDigest: true
  allowedRegistries:
    - registry.example.com
  signature:
    required: true
    trustedIssuer: https://token.actions.example
    trustedIdentity: https://example.com/ci/release
  provenance:
    required: true
    sourceRepository: https://example.com/org/booking
  sbom:
    required: true
  vulnerability:
    denyCritical: true
~~~

This is an illustrative policy, not a standard Kubernetes CRD. Exact schemas, engines, and verification mechanisms depend on the chosen solution. Test policies against valid images, unsigned images, wrong signers, mismatched digests, and missing attestations.

### 13.3. Fail Open or Fail Closed?

Production generally requires failing closed for essential origin/signature policies. However, if the admission service is a centralized dependency, it can become a deployment single point of failure. Implement HA, controlled trust-metadata caching, clear timeouts, and an audited break-glass procedure. Never default to silently permitting any image when the verifier loses connectivity.

## 14. Protecting IaC and Deployment Configurations

### 14.1. IaC Is Part of the Supply Chain

Terraform modules, Helm charts, Kubernetes manifests, policy files, and deployment scripts can open networks, grant IAM rights, disable logging, or run privileged workloads. Review and test them like code:

- Pin providers/modules and dependencies.
- Scan for misconfigurations before applying.
- Review plans and diffs.
- Require approvals for production.
- Separate state and identities per environment.
- Block sensitive IAM/network/storage changes without appropriate approvals.
- Audit applies and executing identities.

### 14.2. Protecting Deployment Repositories

With GitOps, the deployment repository becomes the production control surface. Enforce branch protection, `CODEOWNERS`, signed commits/tags where appropriate, least-privilege bots, and change auditing. Never allow an application pull request to modify production manifests outside the controlled workflow.

### 14.3. Drift Detection

Compare live infrastructure state against declarative configs to detect out-of-band changes. Drift is not always malicious; it can stem from incident response or emergency actions. Identify the owner, reason, reconciliation plan, and audit trail.

## 15. Runtime Verification and Post-Deployment Response

### 15.1. Verifying Running Images

Continuously reconcile runtime workload image digests against promotion manifests and release records. Alert on images running outside allowlists, mutable image tags, or workloads launched under unusual service accounts.

### 15.2. Runtime Controls

- Short-lived workload identities; never bake cloud keys into images.
- Need-based network egress allowlists.
- Read-only filesystems, non-root execution, and minimal capabilities.
- Resource limits and appropriate seccomp/AppArmor profiles.
- Runtime threat detection for anomalous processes/network activity.
- Auditing of Kubernetes API or deployment control-plane calls.
- Segmentation across workloads and namespaces.

### 15.3. When a Compromised Image Is Discovered

1. Identify digest, signer, provenance, source commit, and release timestamp.
2. Locate every workload running the affected digest.
3. Assess secrets, tokens, data access, and network paths that the workload may have used.
4. Quarantine/deny the image and block new deployments.
5. Revoke signing identities/tokens if compromised.
6. Build a clean artifact from verified source/dependencies.
7. Deploy the replacement and verify runtime state.
8. Rotate potentially exposed credentials and investigate persistence.
9. Preserve evidence, SBOMs, logs, and audit trails.

Do not simply delete the image from the registry and close the incident; clusters may still run cached images on nodes, or deployment controllers may still reference old manifests.

## 16. Exception Management and Recoverability

### 16.1. Security Exceptions

Exceptions for findings or artifacts must include:

- Specific finding/policy.
- Affected artifact digest and environment.
- Justification and business owner.
- Compensating mitigations.
- Approver and expiration date.
- Remediation plan.

Never create wildcard exceptions such as "ignore images from this registry" across all projects.

### 16.2. Signing Key Compromise

If a signing key is exposed:

- Revoke or deny the key/identity in the verifier mechanism.
- Determine the time window during which artifacts could have been forged.
- List artifacts by signer and timestamp.
- Pause related promotions.
- Issue a new identity/key and update trust policies.
- Re-sign artifacts from a clean pipeline after verifying source integrity.
- Verify running images and manifests have been updated.

Verifiers must support policy-based key revocation/identity denial. A mathematically valid signature does not mean an artifact remains trustworthy after the signer is compromised.

### 16.3. Registry or CI Outages

Supply-chain DR must protect:

- Mirrors of sources and artifacts in appropriate failure domains.
- Caches of verified dependencies.
- Pinned image digests in deployment manifests.
- Provenance/SBOM/signature evidence stored with artifacts or in an independent store.
- Emergency procedures restricted to pre-approved artifacts.

Do not skip signature verification just because a signing service is temporarily down. Stored evidence and backup verifiers can be used provided validity/revocation can still be checked.

## 17. Observability and Effectiveness Metrics

### 17.1. Metrics to Track

| Category | Metric | Meaning |
|---|---|---|
| Source | Protected branch coverage, review bypasses | Source protection level |
| Dependency | Dependency update age, critical advisory age | Risk remediation speed |
| CI/CD | Ephemeral runner ratio, workflow privileges, secret exposures | Pipeline security posture |
| Build | Reproducibility rate, trusted builder coverage | Build trustworthiness |
| Artifact | Signed artifact coverage, provenance/SBOM coverage | Origin evidence |
| Registry | Immutable digest usage, unauthorized push attempts | Integrity and access control |
| Admission | Rejected unsigned/untrusted images, exception count | Policy enforcement |
| Runtime | Unknown-digest workloads, vulnerable image age | Production exposure |
| Response | Time to quarantine, time to redeploy patched images | Response effectiveness |

### 17.2. Avoiding Metric Cardinality and Data Leaks in Logs

Do not turn every commit, user, package, or image ID into unbounded metric labels. Use aggregated metrics and structured events with appropriate retention and access controls. Logs must never contain tokens, signing secrets, or credentials.

### 17.3. Release-to-Runtime Dashboard

A valuable dashboard links release to runtime:

Source commit → workflow run → build identity → artifact digest → SBOM/provenance → signature → approval → deployment → running digest.

During an incident, responders can trace this chain to scope impact instead of hunting manually across disconnected tools.

## 18. End-to-End Example: Releasing the Booking API

### 18.1. Proposed Pipeline

~~~mermaid
sequenceDiagram
    participant Dev as Developer
    participant Git as Source repository
    participant CI as Trusted CI
    participant Reg as Artifact registry
    participant Gate as Verification / admission
    participant K8s as Production cluster
    Dev->>Git: Pull request
    Git->>Git: Review and required checks
    Git->>CI: Merge approved commit
    CI->>CI: Build, test, scan
    CI->>CI: Generate SBOM and provenance
    CI->>CI: Sign image digest
    CI->>Reg: Push immutable image
    Reg->>Gate: Candidate digest and evidence
    Gate->>Gate: Verify signer, provenance, policy
    Gate->>K8s: Approve deployment
    K8s->>K8s: Admission verifies image
    K8s->>K8s: Run exact approved digest
~~~

### 18.2. Release Record

~~~yaml
release:
  service: booking-api
  sourceCommit: 8f31a7c
  image: registry.example.com/booking/api@sha256:IMAGE_DIGEST
  sbom: sbom://booking-api/sha256:IMAGE_DIGEST
  provenance: attestation://booking-api/sha256:IMAGE_DIGEST
  signerIdentity: https://example.com/ci/release
  environment: production
  approval: change-4821
~~~

This is an illustrative release record. In practice, references must point to integrity-protected evidence; never use placeholder values or store secrets in manifests.

### 18.3. Incident Scenario

A dependency inside an image is found to have a critical vulnerability after production deployment. The team queries SBOMs to identify image digests containing the affected package; checks release records for the commit and builder; locates workloads running that digest; builds a patched dependency version; runs tests/scans; signs and attests the new artifact; promotes the exact digest; admission validates it; and the runtime dashboard confirms the old image is gone.

If source or workflow compromise is discovered instead, expand the investigation to all artifacts signed by the same identity during the affected window rather than only patching a package and rebuilding.

## 19. Common Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Trusting any image in an internal registry | Unauthorized images can be pushed | Signatures, provenance, and registry ACLs |
| Deploying with mutable tags | Tags can be repointed to another image | Pin digests |
| Scanning source only | Misses OS packages and runtime layers | Scan images and generate SBOMs for final artifacts |
| Not locking dependencies | Builds shift unexpectedly | Lockfiles and integrity verification |
| Giving CI jobs production secrets | Malicious dependencies can steal credentials | Isolated runners and short-lived OIDC |
| Using unpinned action tags | Pipeline behavior can change silently | Pin commit digests and review updates |
| Sharing build and deploy permissions | Compromised builds can self-deploy | Separate identities and approvals |
| SBOM not bound to digest | Unclear which image it describes | Bind SBOM/attestation to subject digest |
| Treating a valid signature as sufficient | Signer could be compromised or unauthorized | Verify identity, issuer, provenance, and policy |
| Scanning without admission enforcement | Non-compliant workloads still run | Enforce pre-deploy and at cluster admission |
| Rebuilding separately for production | Tested artifact differs from deployed artifact | Build once, promote the same digest |
| Deleting registry image ends the incident | Nodes still hold cached images and running pods | Quarantine, replace via rollout, and runtime inventory |
| Non-expiring exceptions | Policy erodes over time | Exceptions with owners, scopes, and expirations |

## 20. Well-Architected Evaluation

| Pillar | Questions | Controls and Trade-Offs |
|---|---|---|
| **Operational Excellence** | Can we trace from commit to running image and execute revocation runbooks? | Release records, dashboards, and automation; requires maintaining evidence |
| **Security** | Who can modify source, build, sign, push, and deploy? | Least privilege, OIDC, runner isolation, signing, and admission |
| **Reliability** | Can artifacts be reproduced and recovered during CI/registry outages? | Mirrors, immutable artifacts, recovery procedures; adds storage and operational effort |
| **Performance Efficiency** | Do scanning/verification excessively slow pipelines or startup? | Parallel scans, verified caches, HA admission, and tuned policies |
| **Cost Optimization** | Are too many images/SBOMs/logs retained or redundant scans run? | Criticality-based retention, deduplication, and shared evidence |
| **Sustainability** | Are there unnecessary rebuilds, image transfers, and duplicate scans? | Trusted build caches, artifact promotion, incremental scanning where supported |

A trusted supply chain is not built simply by buying a scanner or turning on image signing. It links identity, source, builders, artifacts, policies, and runtime into an auditable chain of evidence.

## 21. Applied Exercises

### Exercise A — Overwritten Tag

Staging tested image tag `release-42`. Before production deployment, the tag is overwritten with a different image under the same tag name.

**Question:** How do you prevent this?

**Hint:** Use immutable digests in promotion manifests, registry policies blocking tag overwrites, and verify signature/provenance on the exact digest before deploying.

### Exercise B — Exposed CI Secret

A pull request from a fork triggers a workflow holding permissions to read a long-lived cloud access key.

**Question:** Where was the trust boundary violated?

**Hint:** Untrusted code executed inside a job with privileged secrets. Separate workflows, withhold secrets from fork jobs, use isolated runners, and restrict OIDC identities by repository/branch/environment.

### Exercise C — SBOM Mismatches the Image

The pipeline generates an SBOM from source dependency manifests, but the runtime image includes additional OS packages from the base image.

**Question:** Why is the evidence incomplete?

**Hint:** The SBOM does not cover the final artifact. Generate/reconcile the SBOM against the built image digest and bind the subject digest in an attestation.

### Exercise D — Compromised Signer

A signing identity is compromised, yet previously signed images still pass cryptographic signature verification.

**Question:** Should all signed images still be trusted?

**Hint:** No. Revoke/deny the identity by time and policy, identify artifacts from the affected window, investigate the workflow, and reissue clean artifacts.

### Exercise E — Admission Service Unavailable

The cluster cannot reach the verifier while an urgent hotfix needs to be deployed.

**Question:** Should signature verification be disabled cluster-wide?

**Hint:** Do not default to fail-open. Maintain redundant verifiers, integrity-checked evidence caches with validity policies, or scoped/time-bound/approved/audited break-glass limited to previously verified artifacts.

### Exercise F — New CVE in a Transitive Dependency

A vulnerability is disclosed in a package deep in the dependency tree. The team does not know which running images contain it.

**Question:** Which evidence identifies the blast radius quickly?

**Hint:** Digest-bound SBOMs, running workload inventory, release provenance, and dependency advisory mappings. Use them to prioritize exposed workloads, rebuild/promote, and confirm old digests are gone.

## 22. Pre-Production Supply Chain Controls Checklist

- [ ] Source, dependencies, builders, runners, registries, artifacts, and deployment controllers are inventoried.
- [ ] Branch/release protection and owner reviews cover source, workflows, IaC, and deployment configs.
- [ ] Dependencies are locked, integrity-checked, and sourced from trusted registries/namespaces.
- [ ] Build runners are isolated, ephemeral where appropriate, and never share secrets across trust levels.
- [ ] CI jobs hold least privilege; production access uses short-lived/OIDC identities where feasible.
- [ ] Actions, plugins, and toolchains are pinned and updated through reviews.
- [ ] Builds never embed secrets into source, image layers, artifacts, or logs.
- [ ] Container base images come from trusted sources, have explicit digests/versions, and receive updates.
- [ ] Runtime images are minimal, non-root, and use read-only/restricted capabilities where appropriate.
- [ ] Artifacts are identified by digest, and registries enforce ACLs, immutability, and auditing.
- [ ] SBOMs describe final artifacts and bind to exact digests.
- [ ] Provenance proves source, builder, and build context per policy.
- [ ] Signatures are created by authorized identities with revocation/rotation procedures.
- [ ] Deployments verify digest, signature, issuer, provenance, and policy.
- [ ] Admission controls block untrusted images and have HA plus audited break-glass procedures.
- [ ] IaC and deployment manifests are reviewed, scanned, versioned, and checked for drift.
- [ ] Dashboards link source commits to running image digests.
- [ ] Procedures exist to quarantine, rebuild, rotate credentials, and revoke signers after compromise.
- [ ] Exceptions specify owner, rationale, scope, mitigations, and expiration.
- [ ] CI/registry mirrors/restores, signing evidence, and runbooks have been rehearsed.

**Core Takeaway:** software is only trustworthy when an organization can prove production artifacts came from authorized source and builders, contain known dependencies, carry accurate SBOM/provenance, are signed by trusted identities, and are policy-verified before execution. Digest pinning, CI/CD hardening, build/deploy separation, admission controls, and runtime monitoring form continuous layers from commit to production.
