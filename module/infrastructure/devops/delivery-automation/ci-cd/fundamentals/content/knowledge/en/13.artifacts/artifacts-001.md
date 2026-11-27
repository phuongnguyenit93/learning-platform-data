# Distinguishing Build Artifacts from Source Code and Temporary Files

## 1. Why Do We Need to Distinguish Output Types?

A single build can produce many files: JAR files, container images, compiled files, auto-generated source code, test reports, logs, caches, and intermediate working directories. These files do not serve the same role. Some are inputs for building software, some are deployable products, some exist only for diagnostics, and some exist only during the build.

Without a clear distinction, CI/CD pipelines can easily run into issues such as:

- Accidentally deploying source code or temporary files to production.
- Storing the entire workspace as an artifact, increasing storage size and making it hard to identify which files are being released.
- Deploying a stale build file left over from a previous run.
- Building differently in each environment, resulting in a staging artifact that differs from production.
- Inability to trace a release back to the commit and build run that produced it.
- Caches or log files containing sensitive data getting packaged into an artifact.
- When a rollback is needed, the team no longer has the previous artifact and must rebuild from source.

Therefore, it is necessary to distinguish at least four categories: **source code**, **build output**, **release artifact**, and **temporary files**. This is the foundation for controlling what is stored, tested, signed, promoted across environments, and deployed.

Within the scope of **DEVOPS_CI_CD_FUNDAMENTALS**, the goal is to design a traceable release flow from Git events, pipeline-as-code, automated builds and tests to artifact management, environments, quality gates, secrets protection, post-deploy verification, and rollback capability. Correctly identifying build artifacts gives every step in the flow well-defined inputs and outputs.

## 2. Four Concepts to Distinguish

| Category | Nature | Examples | Role |
|---|---|---|---|
| Source code (source) | Content maintained by humans or tools to describe software | Java, TypeScript, configuration, documentation, build scripts | Input managed by Git |
| Build output | Files produced during compilation, packaging, or testing | Classes, JARs, frontend bundles, images, test reports | May be a final product or merely an intermediate output |
| Release artifact | Output that has been selected, verified, identified, and stored for distribution or deployment | Tested JAR, container image by digest, signed package | Unit promoted across environments and deployed |
| Temporary file | Data serving a single processing step that does not need to persist as a long-lived product | Intermediate files, extracted directories, sockets, scratch files, local cache | Can be deleted after the job completes |

Not every build output is a release artifact. A build directory may contain releasable files alongside reports, intermediate files, metadata, and debug files. The pipeline must select the exact outputs to publish.

Several file types play special roles:

- **Auto-generated source code:** may serve as input to a subsequent compilation step, but is usually generated from a schema or original source code. You must decide whether to commit it to Git or regenerate it during the build.
- **Test and scan reports:** serve as evidence of quality and are usually stored as artifacts for auditing, but are not deployable products.
- **Source archive:** a source code package bundled for distribution or to meet release requirements. It is still an artifact, but differs from the binary used to run the application.
- **Debug symbols:** may be needed for production diagnostics, but require separate access controls and retention policies.
- **Cache:** performance optimization data, not proof of origin or an official release.

## 3. Source Code Is Input with History; Artifacts Are Outputs with Identity

Source code is typically managed in Git. A commit identifies the state of content at a point in time and provides change history, authorship, reviews, and links to pull requests.

An artifact is the result of a specific build process. It depends on many factors beyond source code:

- The input commit or source tree.
- Compiler, runtime, and build tool versions.
- Direct and transitive dependencies.
- Build configuration, profiles, and feature flags at build time.
- The builder's operating system, architecture, and execution environment.
- Environment variables allowed to affect the build.
- Scripts, plugins, and actions used by the pipeline.

Thus, knowing the commit alone is not necessarily enough to reproduce the exact artifact. Conversely, having a JAR file without knowing its commit and build environment is not enough to trust it.

Relationships that must be recorded:

~~~mermaid
flowchart TD
    A["Git commit and source tree"] --> B["Pipeline run"]
    C["Toolchain and build configuration"] --> B
    D["Resolved dependency graph"] --> B
    B --> E["Build output"]
    E --> F["Tests and security checks"]
    F --> G{"Passed quality gate?"}
    G -- "No" --> H["Keep reports, fix issues"]
    G -- "Yes" --> I["Select release artifact"]
    I --> J["Digest, metadata, and provenance"]
    J --> K["Artifact repository"]
    K --> L["Promote same artifact"]
    L --> M["Deploy and verify"]
~~~

Each build needs its own unique identifier. For example, the same commit might be rebuilt with a newer toolchain, different dependencies, or different parameters. You should not use only the commit SHA as the artifact name and overwrite previous outputs.

## 4. Where Are Build Outputs Created?

Each build tool follows different output directory conventions. The important part is that the pipeline knows what must be published and what is intermediate data.

| Ecosystem/Tool | Common Directory or Output | Notes |
|---|---|---|
| Maven | target/ | Contains JAR/WAR, classes, generated sources, reports, and intermediate files |
| Gradle | build/ | Contains archives, classes, reports, caches, and task outputs |
| Node.js | dist/, build/ | May be a deployable bundle or the output of a build step |
| .NET | bin/, obj/ | bin holds outputs; obj typically holds intermediate data |
| Go | Binary produced by the build command | Name, architecture, and target directory must be specified |
| Docker/BuildKit | Container image or OCI layout | Images should be tagged and referenced by digest in the registry |
| Terraform | Plan file; state is managed separately | Plans may contain sensitive data; state must be stored in a protected backend and not treated as an application artifact |

These directories are only common conventions, not a guarantee that every file inside them is a release artifact.

For example, with Maven, the target directory may contain:

- The main application JAR file.
- Source or Javadoc JAR files.
- Compiled classes.
- Generated source code.
- Surefire or Failsafe reports.
- Temporary files created by plugins.

If the pipeline uploads the entire target directory, consumers may not know which file is the deployment package. It is better to select the exact verified JAR or WAR file and store test reports separately.

With Gradle, the build directory can contain outputs from many different tasks. You should identify the task that produces the release archive and use that task's output instead of compressing the entire build directory.

## 5. Release Artifacts Must Have a Clear Contract

An artifact is considered ready for release when the team knows precisely:

1. What kind of product it is and what it is used for.
2. Which commit and pipeline run produced it.
3. Which toolchain and dependencies were used to build it.
4. Which checks it has passed.
5. Where it is stored and what identifier references it.
6. Who or which system is authorized to publish and deploy it.
7. How to verify its contents and origin.
8. Its retention period and revocation process.
9. How it can be deployed or rolled back.

An artifact contract for a service can be defined as follows:

| Attribute | Meaning | Example |
|---|---|---|
| Artifact name | Product name | checkout-service |
| Version | Human-readable version | 2.8.1 |
| Type | Format | JAR, OCI image, ZIP |
| Source revision | Source commit | Git commit SHA |
| Build run | Pipeline execution | CI run identifier |
| Digest | Immutable content identifier | SHA-256 or OCI digest |
| Provenance | Evidence of how it was built | Builder, source, parameters |
| SBOM | List of components | SPDX or CycloneDX |
| Test evidence | Verification evidence | Unit, integration, security reports |
| Storage location | Storage repository | Maven repository or container registry |

Not every project needs every field at the same level of detail. However, name, version, source commit, pipeline run, and digest are fundamental information for artifact traceability.

## 6. Artifact Identification: Version, Tag, and Digest

A version name helps humans recognize the product. A digest precisely identifies the contents.

Example:

- Version: 2.8.1
- Image tag: checkout-service:2.8.1
- Image digest: sha256:...

Tags can be reassigned or overwritten depending on registry policy. A digest is computed from the image contents and changes whenever the contents change. Therefore, deployment flows should prefer digests or equivalent immutable identifiers.

For Maven packages or ZIP files, a SHA-256 checksum can be stored alongside the artifact. Upon download, the pipeline or deployment system recomputes the checksum and compares it against the stored metadata.

Key principles:

- Never reuse an already published release version for different content.
- Never overwrite release artifacts.
- Bind the digest to the release record.
- Store human-readable tags alongside digests for verification.
- Verify checksums after downloading or copying between repositories.
- When a rebuild produces a different digest, store it as a new build and investigate the cause.

A digest only identifies content. It does not by itself prove who created the artifact or whether the process is trustworthy. It must be combined with provenance, signatures, and builder policies.

## 7. Distinguishing Artifacts, Caches, and Workspaces

These three concepts are often confused because all of them hold files created during a build.

| Concept | Purpose | Lifecycle | Used for Deployment? |
|---|---|---|---|
| Workspace | Working directory of a CI job | Usually scoped to a single run | Not directly |
| Cache | Holds reusable data to speed up builds | Can persist across multiple runs and be evicted | No |
| Artifact | Stores outputs or evidence of a run | Follows retention and release policies | Yes, if classified as a deployable artifact |

A workspace may contain checked-out source code, downloaded dependencies, temporary files, and outputs. A cache may contain dependencies or reusable build data. An artifact must be selectively chosen, identified, and stored for its intended purpose.

Do not upload workspaces or caches as if they were release products. Doing so can:

- Leak secrets or credentials into the artifact repository.
- Include stale files from previous runs in the package.
- Inflate storage usage.
- Make artifacts non-reproducible or difficult to inspect.
- Cause deployers to pick the wrong file.

Clean the workspace before a build if runners are reused, and ensure the pipeline does not pick up leftover outputs from a prior run.

## 8. Application Artifacts vs. Evidence Artifacts

Not every artifact is deployed. They should be clearly classified so retention and access permissions match their purpose.

| Artifact Type | Examples | Consumer or System |
|---|---|---|
| Deployable artifact | JAR, WAR, container image, frontend bundle | Release pipeline and runtime environment |
| Test evidence | JUnit XML, coverage report, integration test log | Development team and quality gate |
| Security evidence | SAST, dependency scan, container scan, SBOM | Security team and auditors |
| Build metadata | Build manifest, toolchain version, dependency graph | Investigation and reproduction |
| Source package | Source archive or source code package | Source distribution consumers |
| Debug artifact | Symbol files, sanitized crash dumps | Incident investigation team |

Test evidence must be tied to the exact same commit and build run that produced the deployable artifact. If tests run on one build while the pipeline publishes another build, the test report does not prove the quality of the released artifact.

For reports containing sensitive data, restrict read permissions and retention periods. Test logs may contain internal URLs, test data, or accidentally printed credentials.

## 9. Build Once, Promote the Same Artifact

A core principle of CI/CD is to build an artifact once and move that exact same artifact across environments.

Recommended flow:

1. The pipeline fetches source code from a specific commit.
2. Resolves dependencies from controlled sources.
3. Builds the package or image.
4. Runs tests and scans on the releasable output.
5. Computes the digest and generates metadata/provenance.
6. Publishes the artifact to a controlled repository.
7. Deploys to staging using that digest.
8. Verifies behavior and quality in staging.
9. Once criteria are met, promotes the same digest to production.
10. Records the release record and performs post-deploy verification.

If staging and production build separately, differences can creep in due to dependencies, toolchains, timing, or environment variables. In that case, successful testing in staging does not prove the production artifact has the same contents.

Environment configuration should be supplied at deployment time through a controlled mechanism rather than baking production secrets or endpoints into the artifact. The same image can run in staging and production with different configurations, secrets, and permissions.

~~~mermaid
flowchart LR
    A["Reviewed commit"] --> B["Build once"]
    B --> C["Test and scan"]
    C --> D{"Quality gate passed?"}
    D -- "No" --> E["Fix and rebuild"]
    E --> B
    D -- "Yes" --> F["Digest and provenance"]
    F --> G["Artifact repository"]
    G --> H["Deploy staging"]
    H --> I["Verify staging"]
    I --> J{"Approved for promotion?"}
    J -- "No" --> K["Hold and investigate"]
    J -- "Yes" --> L["Deploy same digest to production"]
    L --> M["Post-deploy verification"]
~~~

Promotion does not require creating a new artifact. It changes the status or target usage of the same already-verified artifact.

## 10. Storing Artifacts in the Appropriate Repository

Artifacts should be stored in a repository suited to the product type:

- Maven repository for JAR, WAR, POM, and JVM packages.
- npm registry for JavaScript packages.
- NuGet repository for .NET packages.
- OCI/container registry for images.
- Generic artifact repository for ZIPs, binaries, or other release files.
- Dedicated report storage for tests, scans, and evidence.

A repository manager may support proxy, hosted, and group repositories. For release artifacts, publish and read permissions must be separated. Regular build jobs only need read access to dependencies; release jobs have write access to the designated namespace.

Attributes to consider:

- Authentication and authorization.
- TLS and encryption at rest.
- Immutability or no-overwrite policies.
- Retention and cleanup.
- Replication, backup, and restore.
- Audit logs.
- Vulnerability and license scanning.
- Metadata and provenance.
- Separation of snapshot, staging, and release repositories.

Do not grant the same write permissions to every pipeline. If a test job is compromised, its permissions should not allow replacing a published release artifact.

## 11. Provenance, Signatures, and SBOM

An artifact can have a valid checksum yet still have an unknown origin. To increase trust, record the build process and verify identity.

### 11.1. Provenance

Provenance is information describing where and how an artifact was produced. Provenance may include:

- Source repository and commit.
- Builder or pipeline identity.
- Pipeline run and timestamp.
- Key build parameters or configuration.
- Dependencies or materials used.
- Output artifact identifier.
- Relationships between source, build, and package.

Provenance helps answer: was this artifact genuinely built by an authorized pipeline from a reviewed commit?

### 11.2. Digital Signatures

Digital signatures can be attached to the artifact or its metadata. The deployment system verifies the signature before accepting the package.

You must manage:

- Signing keys or signing identities.
- The scope of systems authorized to sign.
- How public keys are distributed and trusted.
- Key rotation and revocation.
- Verification result logs.
- Procedures for handling artifacts with invalid signatures.

Do not store long-lived signing keys directly in repositories or images. Prefer managed signing services or short-lived credentials where supported by the platform.

### 11.3. SBOM

An SBOM lists the software components contained in an artifact. It helps:

- Identify which artifacts contain a vulnerable dependency.
- Track licenses.
- Support supply chain audits.
- Plan dependency upgrades.
- Link components to released products.

The SBOM must be generated from the artifact or dependency graph corresponding to that build run. Do not attach an SBOM from a different commit or build to a release record.

## 12. Immutable Artifacts and Build Reproducibility

An immutable artifact means published content cannot be altered under the same release identifier. If a fix is needed, the pipeline creates a new version or new digest.

This ensures:

- Deployers know the exact content running.
- Rollback can select an earlier artifact.
- The audit trail cannot be retroactively altered.
- Caches and registries do not change the meaning of a version.
- Digests can be compared between staging and production.

A reproducible build is the ability to produce identical artifact contents from identical inputs and controlled build conditions. Not every project can achieve bit-for-bit reproducibility immediately, but it can be improved incrementally by:

- Pinning toolchains and dependencies.
- Using lockfiles or dependency verification.
- Controlling environment variables that affect the build.
- Normalizing timestamps and metadata when supported by tools.
- Avoiding dynamic content downloads during the build.
- Storing build configuration and provenance.
- Using consistent, managed builders.

Reproducible builds must be distinguished from successful rebuilds. A successful rebuild only shows the process can run again; a reproducible build requires the output to match previous results against defined criteria.

## 13. Securing Artifacts Throughout Their Lifecycle

Artifacts can contain malware, vulnerabilities, sensitive data, or internal information. Security must be applied from creation through deletion.

Key measures include:

- Scanning dependencies and binaries before publishing.
- Scanning container images and checking base images.
- Checking for secrets inside packaged files.
- Avoiding placing real environment config files inside packages.
- Restricting read permissions on sensitive artifacts.
- Signing artifacts or provenance according to policy.
- Deploying by digest.
- Tracking revoked or vulnerable artifacts.
- Having a process to quarantine or block artifacts that are no longer allowed for use.
- Logging who or which identity published, downloaded, and deployed an artifact.

If a compromised artifact is discovered, identify the environments running that digest, halt promotion, assess the impact, and release a replacement. Deleting a tag from a registry does not necessarily revoke copies already downloaded or running.

## 14. Retention, Cleanup, and Artifact Lifecycle

You should neither keep every build file forever nor delete everything immediately after a pipeline runs. Retention policies must distinguish between artifact types and criticality.

| Data Type | Typical Policy Needed |
|---|---|
| Production release artifact | Retain per support lifecycle, audit requirements, and rollback capability |
| Snapshot or development build | Shorter TTL with periodic cleanup |
| Test report | Retain long enough for review and failure investigation |
| Security report and SBOM | Retain per audit and vulnerability management requirements |
| Temporary file | Delete after the job or when the workspace is destroyed |
| Cache | Enforce size limits, TTL, and invalidation procedures |
| Debug symbols | Retain for the diagnostic support window of the version |

Before deleting an artifact, consider:

- Is it currently deployed in production?
- Does any release require it for rollback?
- Are there customer or audit retention requirements?
- Is there a verified backup copy?
- Can it be reproduced from existing source and dependencies?
- Must the SBOM or provenance be kept longer than the binary?

Cleanup must avoid deleting artifacts still referenced by release records or active deployments. Lifecycle policies can be configured by repository, version, and release status.

## 15. Downloading and Deploying Artifacts Safely

The deployment system must know which artifact it is permitted to accept and how to verify it.

A deployment process should:

1. Receive the artifact identifier or digest from the release record.
2. Verify the source repository and namespace.
3. Verify the digest after downloading.
4. Verify signatures and provenance according to policy.
5. Verify the artifact has passed required gates.
6. Fetch environment configuration and secrets from a protected source.
7. Deploy the exact approved digest.
8. Record the release ID, digest, environment, and timestamp.
9. Verify the service after deployment.

Do not let a deploy job look up the latest artifact using a generic tag like latest. That can cause a deployment to pick up content different from what was reviewed or approved.

For container images, deploy by digest. For JARs or ZIPs, store the checksum in release metadata and verify it after download. For signed packages, verify the signature before installation or deployment.

## 16. Artifacts and Rollback

Rollback requires a previously stored, verified artifact that remains compatible with the environment.

When a release fails:

- Identify the currently running digest.
- Identify the previous stable digest.
- Check schema and data compatibility.
- Redeploy the previous artifact or roll forward according to the runbook.
- Verify health, smoke tests, and business metrics.
- Record the rollback event and its root cause.

Do not rebuild from an old commit during an incident and assume the result is identical. Dependencies, toolchains, base images, or metadata may have changed. Redeploying the stored artifact restores the exact previous contents.

Database migrations can make code rollbacks unsafe. If the new version altered the schema or wrote data in a new format, compatibility must be checked before bringing back the old artifact. Some cases require rolling forward or restoring data via a separate procedure.

## 17. Pipeline Example Distinguishing Source, Output, Report, and Release Artifact

The example below is pseudocode illustrating how to select outputs from a Java project. Exact artifact upload syntax depends on the CI platform.

~~~yaml
pipeline:
  checkout:
    output:
      - source_tree
      - commit_sha

  build:
    input:
      - source_tree
    outputs:
      - application_jar
      - generated_sources
      - temporary_classes

  test:
    input:
      - application_jar
    outputs:
      - junit_report
      - coverage_report

  security_scan:
    input:
      - application_jar
    outputs:
      - dependency_report
      - sbom

  publish:
    requires:
      - application_jar
      - test_passed
      - security_policy_passed
    publish:
      - immutable_application_jar
      - sbom
      - build_provenance
    exclude:
      - temporary_classes
      - local_cache
      - workspace
      - secret_files

  deploy:
    input:
      - artifact_digest
    verify:
      - checksum
      - provenance
      - release_approval
~~~

The pseudocode makes clear that the source tree, generated sources, temporary classes, reports, and JAR have different lifecycles. Only the JAR that meets all conditions is selected as the deployable artifact. Reports and SBOMs can be stored separately as evidence; caches and workspaces must not be published as products.

### 17.1. Maven Example

A Maven project may produce a JAR inside target. The pipeline should reference the exact release JAR file instead of uploading the entire target directory. Example commands to inspect files:

~~~powershell
mvn -B clean verify
Get-ChildItem target -Filter "*.jar"
~~~

The second command is a PowerShell example to list JARs; on Linux runners an equivalent command can be used. Do not assume the filename if the project has multiple modules or produces multiple classifiers. Identify the artifact using the project's build configuration and metadata.

### 17.2. Gradle Example

With Gradle, the archive task that produces the JAR can be referenced through the task's output. The pipeline should use the task output or a confirmed pattern instead of compressing the whole build directory.

~~~bash
./gradlew clean build
./gradlew tasks --all
~~~

The build task may produce test reports and other outputs. Inspect the task graph and archive configuration to determine which file is the release artifact. In multi-project builds, specify the exact module and variant.

## 18. Measuring Artifact Management Quality

Several metrics can be tracked to evaluate an artifact pipeline:

- Percentage of builds that produce a valid artifact.
- Percentage of artifacts with complete commit, run ID, digest, and provenance.
- Time from build to publish.
- Percentage of deployments using the exact approved digest.
- Number of artifacts rejected due to scans or policies.
- Error rate when downloading artifacts from the repository.
- Recovery time when a rollback is needed.
- Artifact storage size by type and age.
- Number of unreferenced artifacts not yet cleaned up.
- Number of rebuilds of the same commit producing a different digest.

Metrics should help surface issues rather than becoming targets to game reports. For instance, reducing storage by deleting all old artifacts can eliminate rollback capability. Increasing publish rates by skipping scans weakens quality.

## 19. Common Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Treating the entire build directory as an artifact | Mixes products, reports, and temporary files | Select the exact outputs to publish |
| Deploying directly from the workspace | Poor traceability and risk of using leftover files | Publish the artifact first, then deploy from the repository |
| Using the latest tag as the sole identifier | Contents can change | Store version and digest |
| Rebuilding in each environment | Staging and production may differ | Build once, promote the same artifact |
| Overwriting release artifacts | Loses immutability and audit trail | Create a new version or digest |
| Not storing provenance | Hard to verify origin | Attach commit, builder, and pipeline run |
| Putting secrets into packages | Secrets can spread through registries | Inject configuration and secrets at deploy time |
| Treating caches as artifacts | No guarantee of content or origin | Separate cache, workspace, and release storage |
| No retention policy | Loss of rollback capability or excessive storage usage | Define retention by type and status |
| Rolling back by rebuilding old code | Output may not match the previous version | Redeploy the stored artifact and verify |

## 20. Pre-Publish Artifact Checklist

**Output Classification and Selection**

- [ ] Source code, build outputs, reports, caches, and temporary files are distinguished.
- [ ] The exact file or image to be released is identified.
- [ ] The entire workspace is not uploaded without justification.
- [ ] Artifacts do not contain secrets or sensitive environment configurations.
- [ ] Reports and SBOMs are stored separately as evidence.

**Identification and Traceability**

- [ ] The artifact has a clear name, version, and type.
- [ ] Commit SHA and pipeline run ID are present.
- [ ] Digest or checksum is present.
- [ ] Provenance appropriate to the risk level is present.
- [ ] SBOM or dependency report is present as required.
- [ ] Test and scan results are tied to the same build run.

**Storage and Security**

- [ ] The artifact is published to an appropriate repository.
- [ ] Read and write permissions are separated.
- [ ] Release artifacts cannot be overwritten.
- [ ] TLS, authentication, and audit trails are enabled.
- [ ] Retention, backup, and cleanup policies are in place.
- [ ] The artifact can be verified after download.

**Deployment and Recovery**

- [ ] Staging and production use the same digest.
- [ ] The release record identifies the approved artifact.
- [ ] Post-deploy verification is in place.
- [ ] A previous artifact is available for rollback.
- [ ] Database and data compatibility have been reviewed.

## 21. Conclusion

Source code describes the software and is managed through Git history. Build outputs are whatever the tools generate, which may include products, reports, and intermediate files. A release artifact is an output that has been selected, verified, identified, and stored for distribution or deployment. Temporary files serve only a single processing step and must not be confused with release products.

When a pipeline precisely identifies an artifact and binds it to its commit, build run, digest, provenance, and check results, the team can build once, promote identical contents across environments, and roll back in a controlled manner. This forms the basis for traceable releases, supply chain protection, and maintaining software reproducibility.
