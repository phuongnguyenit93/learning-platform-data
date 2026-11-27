# Recognizing the Pipeline as Part of the Software Supply Chain

## Learning Objectives

After completing this lesson, learners will be able to:

- Explain why a CI/CD pipeline is a high-privilege link in the software supply chain.
- Describe the assets, actors, trust boundaries, and data flows from source code to production.
- Identify common attack vectors across source code, dependencies, build scripts, plugins, runners, caches, artifacts, and credentials.
- Distinguish between application code security and the security of the process that builds and releases the application.
- Apply the principle of least privilege, runner isolation, secret protection, and pipeline change control.
- Design a mechanism to verify artifact provenance and integrity before deployment.
- Build a threat modeling perspective to prioritize controls based on product risk.

## 1. The Software Supply Chain Does Not End at Source Code

When talking about software security, teams often think about bugs in application code: injection, authentication flaws, broken access control, or unsafe data handling. These issues are critical, yet software passes through many other components before reaching users.

A software release is typically produced through a chain of activities:

1. Developers write and modify source code.
2. Git stores history and accepts pull requests.
3. The CI pipeline validates code, downloads dependencies, and runs build scripts.
4. Build tools, compilers, plugins, and runners produce artifacts.
5. Artifacts are stored in a registry or distribution repository.
6. The release pipeline selects an artifact and deploys it to an environment.
7. Operations systems verify the version, monitor, and update it.

All components, people, processes, and services involved in creating, testing, packaging, distributing, and deploying software form the **software supply chain**.

The CI/CD pipeline occupies a special position in this chain. It ingests source code and dependencies, executes build code, may read credentials, produces trusted artifacts, and holds permissions to modify environments. If the pipeline is compromised, an attacker can alter software before it reaches users without needing to directly exploit the running application.

Therefore, pipeline security is part of software supply chain security. A green pipeline does not automatically mean an artifact is safe. You need to know what code the pipeline ran, in which environment, using which dependencies, with what permissions, and what artifact it produced.

## 2. The Pipeline Is a High-Privilege Component

A pipeline is typically granted far more privileges than a normal application process:

- Reading repositories and source branches.
- Downloading packages or images from registries.
- Accessing signing keys or credentials to publish artifacts.
- Reading environment secrets.
- Pushing images, packages, or releases to distribution repositories.
- Deploying to clusters or servers.
- Modifying configurations, infrastructure, or feature flags.

A workflow might simultaneously execute code supplied by a pull request while holding a token with write access to the repository or production credentials. When these two conditions exist together, untrusted code can abuse the pipeline's privileges.

Think of the pipeline as a **control plane** for software delivery. It decides which code is tested, which artifacts are produced, who is allowed to release, and which environments are changed.

This creates two requirements:

- Protect the pipeline from unauthorized modification or execution.
- Limit the blast radius if a job, plugin, dependency, or runner is compromised.

Do not assume a pipeline is safe just because it runs on a managed CI service. The provider may secure the underlying platform, but workflow configuration, actions/plugins, scripts, dependencies, token permissions, and secret handling remain the team's responsibility.

## 3. Viewing the Entire Supply Chain as a Trust Graph

A useful way to understand pipeline security is to map the components and the trust relationships between them.

~~~mermaid
flowchart LR
    A["Developer / Reviewer"] --> B["Source repository"]
    B --> C["CI workflow"]
    C --> D["Runner / Build environment"]
    D --> E["Build tools, plugins, dependencies"]
    E --> D
    D --> F["Artifact + test evidence"]
    F --> G["Artifact registry"]
    G --> H["Release / Deployment pipeline"]
    H --> I["Target environment"]
    I --> J["Running service"]
    C --> K["Secrets / identity provider"]
    H --> K
    K --> H
~~~

The diagram shows that an artifact does not automatically become trustworthy just because it resides in a registry. Trust depends on the entire path:

- Is source code reviewed and protected?
- Are workflows subject to change control?
- Are runners clean and isolated?
- Do dependencies come from trusted sources?
- Are build tools and plugins version-controlled?
- Is the artifact linked to the commit and build evidence?
- Does the registry protect write permissions and immutability?
- Does the deployment pipeline verify the artifact before deploying?

If any single link can be silently altered, evidence at other links may lose its value.

## 4. Assets to Protect in a Pipeline

Threat modeling begins by identifying assets. Production artifacts are not the only valuable assets; many pieces of data and permissions inside the pipeline can help an attacker escalate access further.

| Asset | Examples | Impact if Compromised |
|---|---|---|
| Source code | Repository, branch, tag | Injecting malicious code or altering logic |
| Pipeline definition | Workflow YAML, build script | Changing test conditions or release behavior |
| Build environment | Runner, container, workspace | Tampering with code or artifacts during build |
| Credentials | Token, SSH key, cloud credential | Reading data or performing unauthorized actions |
| Dependency | Package, plugin, action, base image | Introducing malicious code at build time or runtime |
| Cache | Dependency cache, build cache | Poisoning reused data |
| Artifact | JAR, image, package, binary | Releasing altered software |
| Provenance/evidence | Build metadata, test report, attestation | Falsifying evidence of origin |
| Registry | Package/image repository | Replacing, deleting, or distributing artifacts |
| Deployment identity | Service account, workload identity | Modifying target environments |
| Audit log | Run history, approval, deployment record | Hiding tracks or hindering investigation |

You must determine which assets require confidentiality, which require integrity, and which require availability. For example, tokens require confidentiality and revocability; artifacts require integrity; logs require integrity and accessibility during investigations.

## 5. Identifying Actors and Trust Boundaries

A pipeline can receive inputs from multiple sources with varying levels of trust.

Common actors include:

- Internal developers.
- Contributors from forks or external repositories.
- Reviewers and maintainers.
- Bot or automation accounts.
- CI/CD providers.
- Package, plugin, or action providers.
- Production operators.
- Attackers who have compromised an account, dependency, or runner.

Not all changes carry the same trust level. A pull request from a fork may contain untrusted code and workflows. A protected branch merged after review has a higher trust level, though it still requires checks. A package downloaded from a public registry must also be treated as an external input.

Trust boundaries to identify:

1. From a developer's machine to the repository.
2. From an external pull request to a CI runner.
3. From a workflow definition to a runner with execution privileges.
4. From a runner to package registries and external services.
5. From a build job to the artifact registry.
6. From the artifact registry to the release pipeline.
7. From a deployment identity to the target environment.
8. From the CI system to the secret manager or cloud identity provider.

At each boundary, ask: what data crosses it, who controls it, can it be modified, and what permissions are used?

## 6. Common Attack Vectors

### 6.1. Modifying Workflows or Build Scripts

An attacker may modify a workflow to skip tests, run commands that download external code, exfiltrate secrets, or publish an unexpected artifact.

Conditions that enable this attack include weak branch protection, lack of mandatory reviews, or production pipelines running from uncontrolled branches.

Appropriate controls:

- Protect branches and sensitive workflow files.
- Require review from pipeline owners or the platform team.
- Restrict workflow permissions.
- Treat workflow changes like security-sensitive code changes.
- Separate regular build permissions from production release permissions.

### 6.2. Executing Untrusted Code from Pull Requests

Builds and tests typically execute code supplied by a pull request. That code can run scripts, plugins, test helpers, or dependencies with arbitrary behavior inside the runner.

If the job has secrets or high-privilege tokens, untrusted code can attempt to read or exfiltrate them.

Appropriate controls:

- Do not expose sensitive secrets to jobs running code from forks or untrusted sources.
- Use read-only tokens for pull request validation jobs.
- Run jobs on ephemeral or isolated runners.
- Separate workflows that test external code from high-privilege release workflows.
- Grant write permissions and release credentials only after changes pass trust requirements.

### 6.3. Compromised Dependencies or Plugins

Applications often fetch packages, plugins, actions, or base images from external sources. If a component is hijacked or replaced, malicious code can execute during the build.

Risks include typosquatting packages, dependency confusion, compromised maintainer accounts, trojanized releases, and overly permissive plugins.

Appropriate controls:

- Manage dependency and plugin versions.
- Use trusted registries/repositories with clear namespace rules.
- Verify checksums, signatures, or verification metadata when supported by the ecosystem.
- Scan dependencies and images.
- Review changes to sensitive dependencies.
- Restrict network access and secrets available to build jobs.

### 6.4. Compromised or Stateful Runners

Self-hosted runners can retain workspaces, processes, credentials, or files from previous runs. If jobs of different trust levels share the same machine, a later job can read or modify leftover data.

A compromised runner can also tamper with post-build artifacts, steal tokens, or interfere with subsequent jobs.

Appropriate controls:

- Prefer ephemeral runners or clean workspaces for sensitive jobs.
- Isolate jobs by repository, branch, and trust level.
- Purge credentials and temporary data after a job completes.
- Keep runner images updated and restrict OS-level permissions.
- Never run untrusted jobs on machines with production access.
- Monitor runner behavior and lifecycle.

### 6.5. Cache Poisoning

Caches are reused across runs to speed up builds. If an untrusted job can write to a cache that a trusted release job later consumes, malicious data can be reused.

Appropriate controls:

- Partition caches by repository, branch, or trust level.
- Prevent jobs from forks from writing to caches consumed by trusted release jobs.
- Bind cache keys to lockfiles, toolchains, and configurations.
- Maintain a procedure to clear or invalidate caches when poisoning is suspected.
- Never treat a cache as the authoritative source for release artifacts.

### 6.6. Artifact Substitution or Evidence Forgery

If a registry allows overwriting tags or a deployment pipeline only checks tag names, an artifact can be swapped after testing. Test reports may also no longer correspond to what gets deployed.

Appropriate controls:

- Use digests or immutable identifiers.
- Protect registry write permissions.
- Bind artifacts to commits and build runs.
- Store provenance and test evidence.
- Verify signatures or attestations against policy before deploying.
- Promote the exact same tested artifact across environments.

## 7. Secrets and Identities Are Critical Control Points

Pipelines often need credentials to publish packages, sign artifacts, access cloud resources, or deploy. If a single shared administrative token is used across jobs, compromising one step can have widespread impact.

### 7.1. Least Privilege

Each job should only have the permissions required for its specific task:

- Lint and unit test jobs usually only need read access to source code.
- Publish jobs need write access only to the designated artifact repository.
- Staging deploy jobs need access only to staging.
- Production deploy jobs require a dedicated identity and additional safeguards.
- Reporting jobs should not receive deployment permissions.

Do not grant repository write access, cloud admin rights, or production secrets to an entire workflow if only one step needs them.

### 7.2. Short-Lived Credentials

When supported by the platform, prefer workload identity or OIDC to exchange a job's identity for short-lived credentials. This reduces the need to store long-lived tokens in CI.

Credentials should be scoped by:

- Repository or project.
- Workflow or job.
- Protected branch or tag.
- Target environment.
- Audience and lifetime.
- Specific permissions on the cloud provider or registry.

Do not rely solely on self-declared workflow names. The provider must verify claims and corresponding trust conditions.

### 7.3. Secret Management

When static secrets must be used:

- Store them in a secret manager or the platform's secret vault.
- Expose them only to the jobs that need them.
- Never pass them on command lines or print them to output.
- Avoid dumping the entire environment.
- Rotate and revoke them at any sign of exposure.
- Never provide them to pull requests from forks or untrusted sources.
- Inspect logs, artifacts, and caches that might inadvertently capture sensitive data.

Secret masking is only a defense-in-depth layer. Never treat it as a guarantee that every secret value will automatically be redacted across all log formats.

## 8. Protecting Pipeline Definitions and Review Processes

Pipeline as code enables configurations to be reviewed, versioned, and audited, but it also turns workflows into executable code running with CI privileges.

A small change in a workflow can:

- Skip required tests.
- Add an external action.
- Alter branch filters.
- Grant write permissions to a token.
- Expose a secret to a new job.
- Change where artifacts are published.
- Trigger deployments on inappropriate events.

Therefore:

- Enforce branch protection on main and release branches.
- Require owner reviews for workflows, build scripts, and sensitive policies.
- Restrict default token permissions.
- Pin critical actions or plugins to immutable revisions when supported by the platform.
- Review version updates to actions, runner images, and build tools.
- Do not allow untrusted contributors to alter release policies.
- Record the workflow revision that produced an artifact.

A reviewed workflow file does not guarantee every script it invokes is safe. You must examine the actual scripts, plugins, dependencies, and actions executed.

## 9. Isolating Jobs and Runners by Trust Level

Isolation limits the impact if a build step is compromised.

A simple model:

| Job Type | Code Source | Recommended Permissions | Recommended Runner |
|---|---|---|---|
| Pull request validation | Potentially from a fork | Read-only, no production secrets | Ephemeral, isolated |
| Build on protected branch | Reviewed code | Read dependencies, publish artifacts if needed | Ephemeral or trusted runner pool |
| Security scan | Specific source/artifact | Read artifacts and metadata | Network/privilege-restricted runner |
| Release | Verified artifact | Controlled release permissions | Trusted runner, ephemeral if available |
| Production deploy | Approved artifact and snapshot | Scoped to a single environment | Dedicated runner and identity |

Untrusted pull request jobs should never run on persistent runners that have access to organizational servers, registries, or secrets.

When using self-hosted runners, determine:

- Are runners reused across repositories or tenants?
- Is the workspace cleaned after every job?
- Can background processes survive after a job finishes?
- Can jobs access metadata services or internal networks?
- Who is allowed to register new runners or modify runner labels?
- How are runner images updated and verified?

Runner isolation is not just about spinning up a container. Containers may still share the host's kernel, network, or credentials. Isolation depth must match the untrusted nature of the workload.

## 10. Dependencies, Actions, and Build Tools Are Supply Chain Inputs

A pipeline does not only build project code. It also executes many external components:

- Packages from Maven, Gradle, npm, PyPI, or other registries.
- Build tool plugins.
- CI actions, reusable workflows, or extensions.
- Base images and toolchains.
- Install scripts and tools downloaded during the build.

Each component can execute code or affect artifact contents.

A baseline dependency policy should include:

1. Defining trusted package sources and namespaces.
2. Pinning versions of critical dependencies, plugins, and actions.
3. Using lockfiles or dependency locking when supported by the ecosystem.
4. Verifying checksums/signatures or using dependency verification.
5. Scanning for vulnerabilities and tracking support status.
6. Reviewing changes to packages with broad privileges or scope.
7. Restricting job network egress where possible.
8. Recording the component inventory inside the artifact when required.

Pinning by tag reduces surprises, but tags can still be mutable in some systems. For actions or images that can change, use commit SHAs or immutable digests as supported by the platform, along with a reviewed update process.

## 11. Artifacts Need Provenance and Integrity

Artifacts are the outputs tested and delivered to environments. You must ensure that the deployed artifact is the exact artifact that was built and verified.

A trustworthy flow should link:

- Source repository and commit.
- Workflow revision and run ID.
- Build tools, compiler, and dependency graph.
- Test, scan, and policy results.
- Artifact digest.
- SBOM or component inventory when needed.
- Provenance or attestation describing how the artifact was built.
- Signatures if required by policy.

**Provenance** is information describing the origin and creation process of an artifact, such as source code, builder, workflow, and build parameters. An **attestation** is a structured statement about an object or process, typically authenticated via a signature or corresponding trust mechanism.

An **SBOM (Software Bill of Materials)** is an inventory of software components contained in an artifact or product. SBOMs help inspect components and assess exposure when new vulnerabilities emerge.

These concepts complement one another:

- Digests identify exact artifact contents.
- Signatures verify the signing source and integrity.
- Provenance describes how the artifact was built.
- SBOMs list the components inside the artifact.
- Test evidence shows which checks ran and their outcomes.

Having an SBOM or signature should not be treated as absolute proof that software is secure. You must verify the generation source, policies, check coverage, and validity of the evidence.

## 12. Pre-Deployment Verification

The release pipeline must verify artifacts and evidence before gaining permissions to affect an environment.

Questions to verify:

- Does the artifact digest match the release request?
- Does the artifact come from a trusted registry?
- Are the commit and repository within allowed sources?
- Does provenance indicate an approved builder/workflow?
- Is the signature valid and is the signer trusted?
- Are test and scan evidence bound to the exact digest or commit?
- Has the artifact been revoked or flagged with new alerts?
- Is the approval tied to the exact artifact, configuration, and environment?

If any required evidence is missing or cannot be verified, the pipeline must halt according to policy. A tag named `release` or a green workflow status should not be considered sufficient to deploy.

The **build once, promote the same artifact** principle reduces the risk of staging testing one package while production receives another. Environment configurations may differ, but the artifact must be uniquely identified and kept unchanged across promotion stages.

## 13. Protecting Caches and Intermediate Data

Caches, workspaces, logs, and temporary files are also part of the supply chain.

Risks may include:

- Caches written by untrusted jobs.
- Subsequent jobs reading leftover files or credentials.
- Temporary artifacts containing secrets or sensitive data.
- Logs recording commands with tokens.
- Scan reports exposing internal paths or non-public details.
- Workspaces being modified after an artifact is checked.

Baseline safeguards:

- Partition caches along trust boundaries.
- Tie cache keys to lockfiles and toolchains.
- Never store secrets in caches.
- Clean workspaces and credentials after jobs.
- Limit retention periods for logs and intermediate artifacts.
- Restrict read permissions on reports and logs.
- Publish artifacts only from steps with clear lineage.
- Verify digests before reusing artifacts.

Do not use caches as a release repository. Caches are optimized for performance and can be evicted or rebuilt; release artifacts require dedicated storage, retention, and access controls.

## 14. Threat Modeling a Pipeline

Threat modeling helps shift from generic checklists to controls grounded in realistic attack paths.

You can start with five questions:

1. **What are we protecting?** Which assets matter most: source, secrets, artifacts, registries, or production?
2. **Who can affect it?** Developers, external contributors, maintainers, bots, vendors, or attackers?
3. **Where are the trust boundaries?** Where do untrusted inputs enter privileged runners or jobs?
4. **What can go wrong?** Malicious code running in builds, stolen secrets, swapped artifacts, forged evidence, or unauthorized deployments?
5. **How do we know and respond?** What logs, alerts, revocation, rollback, and investigation procedures exist?

STRIDE can be used to review threat categories:

| Category | Examples in CI/CD |
|---|---|
| Spoofing | Impersonating a workflow, runner, publisher, or identity |
| Tampering | Modifying source, pipeline, cache, artifact, or deployment manifest |
| Repudiation | Lacking audit trails to determine who made a change or release |
| Information disclosure | Leaking secrets, tokens, logs, or internal data |
| Denial of service | Exhausting runners, quotas, or registries |
| Elevation of privilege | A pull request job gaining write or production permissions |

STRIDE is a taxonomy for asking questions, not a checklist proving a system is secure. Every finding should be tied to an asset, exploitation conditions, impact, and concrete controls.

## 15. Example Attack Scenario

Suppose a repository allows pull requests from forks. A workflow runs unit tests on every pull request. The job is granted a token with repository write permissions and a secret used to publish packages.

A malicious pull request can modify a test script or build script to execute commands inside the runner. Because the job can read secrets, that code can exfiltrate the token. The attacker can then use the token to tamper with releases or publish unauthorized packages.

The root cause chain is not a single bug:

1. Untrusted code executes in the runner.
2. The job receives unnecessary secrets.
3. The token holds overly broad permissions.
4. The runner or network is insufficiently isolated.
5. The publish process is not separated from pull request checks.
6. The artifact registry does not enforce publisher verification.

A safer design:

- Pull requests from forks run checks with read-only permissions and no sensitive secrets.
- Runners are ephemeral and hold no credentials from prior jobs.
- Release workflows run only after code is accepted into a protected branch.
- Publish jobs receive short-lived identities scoped strictly to writing to the target repository.
- Artifacts are bound to digests and provenance.
- Production deployments use only verified and approved artifacts.

The lesson is that multiple layers of control must work together. Masking secrets in logs alone does not stop malicious code from reading secrets in process memory. Branch protection alone does not prevent compromised dependencies. Signing artifacts alone does not prove an artifact was built from the right code if the signer or builder was compromised.

## 16. Pipeline Model with Clear Security Boundaries

A pipeline can be separated into distinct trust zones:

~~~mermaid
flowchart TD
    A["Untrusted pull request"] --> B["Read-only validation job"]
    B --> C["Test results"]
    C --> D["Protected branch after review"]
    D --> E["Trusted build job"]
    E --> F["Artifact + provenance + SBOM"]
    F --> G["Protected artifact registry"]
    G --> H["Release verification"]
    H --> I{"Digest, signature, policy and evidence valid?"}
    I -- "No" --> X["Block release and alert"]
    I -- "Yes" --> J["Environment approval / policy"]
    J --> K["Deploy with scoped identity"]
    K --> L["Post-deploy verification"]
~~~

Key characteristics of this model:

- Jobs handling untrusted code have no publish or deploy permissions.
- Trusted builds run on sources that have passed review requirements.
- Artifacts are built once and stored in a protected registry.
- The release pipeline verifies digests and evidence before obtaining deployment permissions.
- Deployment identities hold permissions only for the required environment.
- Deployment outcomes are verified and recorded.

In practice, there may be multiple workflows and platforms. Security boundaries must be enforced through permissions, identities, runners, registries, and policies—not merely by naming stages.

## 17. Prioritized Rollout Order for Controls

Not every organization can deploy every advanced mechanism at once. You can start with the controls that reduce the greatest risk first.

| Priority | Control | Goal |
|---|---|---|
| 1 | Protect branches and sensitive workflows | Prevent unauthorized pipeline changes |
| 2 | Job-scoped tokens and permissions | Reduce blast radius when a job is compromised |
| 3 | Withhold secrets from untrusted code | Prevent exfiltration from pull requests |
| 4 | Clean and isolated runners | Reduce persistence and cross-job contamination |
| 5 | Pin and review dependencies/actions/plugins | Reduce risk from external components |
| 6 | Protect registries and use immutable digests | Prevent artifact substitution |
| 7 | Provenance, SBOM, and signatures as needed | Increase traceability and verification |
| 8 | Pre-deployment verification | Deploy only policy-compliant artifacts |
| 9 | Auditing, alerting, and incident response | Detect and handle incidents |

This order is a suggested priority, not a rigid rule. Organizations with strict compliance requirements or high risk profiles may need provenance and artifact signing from the outset.

## 18. Connecting with Supply Chain Frameworks

Several frameworks and initiatives help systematize supply chain security:

- **SLSA (Supply-chain Levels for Software Artifacts):** provides assurance levels for artifact creation processes and provenance. It can be used to evaluate builders, build processes, and tamper resistance.
- **NIST SSDF:** outlines secure software development practices across the entire lifecycle, including securing development environments and release processes.
- **SBOM:** provides a software component inventory to support vulnerability management and component accountability.
- **Sigstore and signing/attestation mechanisms:** support signing and verifying artifacts or evidence under appropriate trust models.

Never slap on a "SLSA compliant" or "has SBOM" label as proof that a pipeline is secure. You must specify the framework version, exact requirements, scope of application, and actual evidence. Frameworks complement your threat model and internal policies; they do not replace understanding your own product's pipeline architecture.

## 19. Metrics and Evidence for Observing Pipeline Security

Pipeline security must be operated continuously. You can track:

| Metric / Evidence | What to Observe |
|---|---|
| Workflow change review | Do pipeline changes have the right reviewers and policy checks? |
| Token permission | Which jobs hold write or production permissions? |
| Secret exposure | Which jobs receive secrets, and are secrets leaking into logs/artifacts? |
| Runner lifecycle | Are runners recreated, patched, and cleaned after jobs? |
| Dependency status | Do dependencies, plugins, or actions have vulnerabilities or revoked versions? |
| Artifact provenance | Is the artifact linked to a trusted commit and builder? |
| Signature verification | Does the release verify signers and digests? |
| Registry audit | Who published, retagged, or deleted artifacts? |
| Deployment evidence | Which artifact, config revision, and identity performed the deployment? |
| Incident response | Time to revoke credentials, block releases, and recover |

Do not just count the number of security scanning tools. You need to know which alerts are acted upon, which permissions are actually used, and whether production can be traced back to the exact source that built the artifact.

## 20. Checklist for Recognizing the Pipeline as Part of the Supply Chain

When assessing a pipeline, check:

- [ ] Mapped the flow from source to artifact registry and production.
- [ ] Identified critical assets and owners.
- [ ] Classified input sources by trust level.
- [ ] Identified trust boundaries across pull requests, runners, registries, and deployments.
- [ ] Workflows and build scripts are protected by reviews and branch policies.
- [ ] Jobs processing untrusted code receive no unnecessary secrets or write permissions.
- [ ] Tokens are scoped per job and environment.
- [ ] Short-lived credentials or workload identities are used where appropriate.
- [ ] Runners are isolated, updated, and cleaned of state after jobs.
- [ ] Dependencies, plugins, actions, and base images have controlled sources and versions.
- [ ] Caches are partitioned by trust level and contain no secrets.
- [ ] Artifacts use immutable digests and registries enforce write access controls.
- [ ] Provenance, SBOMs, or signatures are generated as required.
- [ ] Release pipelines verify artifacts and evidence before deploying.
- [ ] Deployment identities hold only required permissions.
- [ ] Logs and audit trails support traceability without leaking secrets.
- [ ] Procedures exist to revoke credentials, block releases, and handle suspected artifacts.

## 21. Self-Assessment Exercise

A development team has the following pipeline:

- Every pull request runs on a shared self-hosted runner.
- Test jobs receive a token with repository write access to fetch private submodules.
- Builds download dependencies and actions using mutable tags.
- Artifacts are published with the `latest` tag.
- The release job deploys `latest` to production without checking digests or provenance.
- Logs dump all environment variables when a build fails.

Analyze:

1. Which assets are at highest risk?
2. Which trust boundaries are bypassed when pull requests run on a shared runner?
3. What mechanisms or restrictions can replace the repository write token?
4. What risks do mutable tags on dependencies and actions introduce?
5. Why is the `latest` tag insufficient to identify a tested artifact?
6. What evidence should the release pipeline verify?
7. What data might full environment logs expose?
8. How should validation, trusted build, and production deployment workflows be separated?
9. If a runner is suspected of compromise, how should you isolate the runner, revoke credentials, and identify affected artifacts?

A strong answer traces the attack path from untrusted input to privileges and artifacts, then proposes controls at each boundary. Do not merely list security tools; explain the protected asset and the risk each control mitigates.

## Conclusion

A CI/CD pipeline is a high-privilege link in the software supply chain because it executes code, consumes dependencies, accesses credentials, produces artifacts, and modifies environments. Pipeline security must therefore cover source code, workflows, runners, plugins, dependencies, caches, secrets, registries, and deployment identities.

Start by identifying assets, actors, and trust boundaries. Then apply least privilege, isolate jobs, protect secrets, govern dependencies, use immutable artifacts, and verify provenance before deployment. When every step produces verifiable evidence and an audit trail, teams can trace production software back to its exact origin while containing the blast radius if any single link is compromised.
