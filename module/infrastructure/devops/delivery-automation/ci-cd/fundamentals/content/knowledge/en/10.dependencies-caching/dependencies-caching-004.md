# Distinguishing Speedup Caches from Deliverable Artifacts

In CI/CD, both caches and artifacts can contain files produced during a build, yet they serve two distinct purposes. **A cache speeds up subsequent runs** by reusing regenerable data. **An artifact is an output that must be stored, handed off, tested, released, or traced** after a job finishes.

If a cache is treated as storage for release outputs, a pipeline can lose builds when the cache expires or is purged. If artifacts are used to cache every dependency, the system can store excessive data, transfer unnecessary files, and slow jobs down. Therefore, CI/CD architecture must clearly define which data is regenerable, which data is a deliverable output, who can read or write each, and how long each must be retained.

This lesson explains the boundary between caches and artifacts, how it applies to dependencies and build outputs, how to design cache keys, hand off artifacts between jobs, protect integrity, and trace release outputs. The goal is to make pipelines faster while ensuring the tested build is the exact build delivered and deployed.

## 1. Understanding the Roles of Caches and Artifacts

A **cache** is temporary storage to avoid repeating expensive work. A pipeline can restore a cache on a later run if the cache key matches and the data still exists. Caches can expire, be evicted, be replaced, or fail to restore; therefore, a job must be able to proceed by regenerating data when the cache is absent.

Examples of caches:

- Downloaded dependency packages from Maven, Gradle, npm, pip, or another package manager.
- Intermediate compilation outputs reusable when inputs have not changed.
- Layers or helper data for container builds.
- Caches of compilers, test runners, or static analysis tools.
- Precomputed data serving subsequent builds.

An **artifact** is a meaningful output of a job or pipeline, stored for consumption by another step, download by users, release, or evidence. An artifact must be tied to the run and inputs that produced it.

Examples of artifacts:

- Built JAR, WAR, ZIP, or application package files.
- Container images stored in a registry.
- Test reports, coverage reports, and security scan results.
- Deployment packages, manifests, and versioned generated configuration files.
- SBOMs, signatures, provenance, or release metadata.
- Binaries transferred from a build job to a test or deploy job.

Two questions serve as a rule of thumb:

- If the data disappears, can the job regenerate it from managed source, dependencies, and configuration? If yes, that data usually belongs in a cache.
- If the data disappears, does the pipeline lose tested outputs, evidence, or deliverable packages? If yes, that data must be managed as an artifact.

This classification is based on purpose. The same file type can play different roles depending on usage. For example, an intermediate JAR may be stored in a build cache for reuse, whereas a tested JAR meant for release must be stored as an artifact with an explicit identity and appropriate retention period.

## 2. Comparing Caches and Artifacts

| Criterion | Cache | Artifact |
|---|---|---|
| Purpose | Speed up repeatable work | Deliver outputs and evidence |
| Necessity | Job must still succeed without it, albeit slower | Downstream steps cannot proceed properly if missing |
| Lifecycle | Can expire, be evicted, or be replaced | Has a retention policy based on value and release requirements |
| Reproducibility | Regenerable from managed inputs | Must preserve the exact generated and verified output |
| Identity | Typically based on a cache key | Tied to pipeline run, commit, version, and digest |
| Immutability | Can change or be updated per key | Should be immutable once created and published |
| Usage | Restores data before execution | Transfers outputs across jobs, archives, or deploys |
| On failure | A cache miss usually only slows the run | Missing or invalid artifacts must fail the pipeline |
| Security | Requires controlling write sources and sharing scope | Requires controlling read/write access, integrity, and provenance |

A cache is an optimization. An artifact is a delivery contract. A pipeline must work properly with an empty cache, yet must stop if a required artifact is missing, the wrong version, or fails verification.

Do not rely on a directory named `cache` or `artifacts` to decide the nature of data. Examine how the pipeline uses the data, how it is identified, its retention policy, and the consequences if it is lost.

## 3. Distinguishing Three Common Categories of Data

Within pipelines, three groups are easily confused:

1. **Managed dependencies:** libraries or packages used by the application, declared in manifests and lockfiles, fetched from trusted package sources.
2. **Caches:** reusable copies or intermediate outputs that cut download and computation times.
3. **Artifacts:** outputs of a specific build or test run, handed off to subsequent steps or stored as evidence.

Example in a Java project:

- `build.gradle` or `pom.xml` declares dependencies.
- Locking or dependency constraints control selected versions.
- Gradle or Maven caches store downloaded files and some intermediate outputs.
- `build/libs/application.jar` is produced after building.
- The pipeline uploads the tested JAR as an artifact, and the deploy job downloads that exact artifact.

The package registry remains the system of record for published packages. A package manager's cache is merely a local or remote copy for faster downloads. If the cache is cleared, the package manager must be able to re-download dependencies from configured sources.

A container image can also play multiple roles. Layer caches speed up image builds; an image pushed with a digest to a container registry and deployed is a release artifact. Do not rely on a layer cache as proof that a release image was safely stored.

## 4. Caching Dependencies to Reduce Download Time

Installing dependencies often accounts for a significant portion of CI runtime. Every clean run may re-download hundreds of packages or libraries. Caching preserves downloaded archives for reuse in later jobs.

### 4.1. Caching Package Manager Data

Examples of commonly cached data:

| Ecosystem | Cacheable Data | Inputs to Consider |
|---|---|---|
| Java / Gradle | Dependency artifacts and metadata in Gradle user home | Gradle wrapper, dependency declarations, lockfile, repository config, JDK |
| Java / Maven | Maven local repository | POM, dependency versions, applicable Maven settings, JDK |
| Node.js | Package manager download cache | Lockfile, Node and package manager versions |
| Python | Package download and wheel cache | Lockfile/requirements, Python version, platform |
| .NET | NuGet package cache | Project files, lockfile, SDK version |
| Container build | Layer cache | Dockerfile, build context, base image, and build arguments |

Caching the entire working directory is not always advisable. For instance, in Node.js, caching the package manager's download cache is usually safer and cleaner to reproduce than preserving `node_modules` across different OSes or runtime versions. With Gradle, dependency caches and build caches can be cached using Gradle's mechanisms, provided the scope and validity conditions of each data type are understood.

### 4.2. Locking Dependencies Before Caching

Caching is meaningful only when dependency inputs are stable. If a manifest allows picking the latest version or dependencies update without locking, two runs can use different versions even when source code is unchanged.

Best practices:

- Use lockfiles or the ecosystem's dependency locking mechanism.
- Declare toolchain versions explicitly.
- Define source repositories and dependency policies.
- Record runtime, compiler, and build tool versions.
- Review dependency changes like source code changes.
- Verify checksums or signatures when supported by the ecosystem.

Caching reuses downloaded packages, but does not replace lockfiles or dependency management policies.

### 4.3. Cache Misses Must Be Normal Operation

A job must never rely on a cache always existing. On a cache miss, the pipeline must fetch dependencies from valid sources and continue.

If a cache miss causes a build failure, the pipeline may be treating the cache as the sole data source. In that case, move the required data to an appropriate package registry or artifact store, keeping the cache strictly in its speedup role.

## 5. Designing Cache Keys

A cache key is an identifier used to look up cached data matching a job's inputs. A key that is too broad can restore incompatible data; a key that is too narrow causes frequent cache misses and reduces effectiveness.

A cache key should reflect inputs that can alter cache contents, such as:

- Operating system and CPU architecture.
- Runtime or JDK version.
- Compiler and build tool versions.
- Lockfile or dependency manifest.
- Build configuration and feature flags affecting output.
- Module or dependency scope.
- Cache format version if storage structure changes.

Conceptual key composition example:

~~~text
cache-key =
  os
  + architecture
  + runtime-version
  + build-tool-version
  + hash(dependency-lockfile)
  + cache-schema-version
~~~

For example, a Java project's dependency cache can change when `gradle-wrapper.properties`, lockfiles, or the JDK change. If the key only depends on branch name, different dependency states may share the same cache without sufficient differentiation.

### 5.1. Exact Keys and Fallback Keys

Some platforms allow restoring a cache by exact key or using prefix/fallback keys. Fallbacks can fetch the closest match and update the cache under the new key, provided compatibility risks are understood.

- Exact keys fit cases where cached contents must match inputs completely.
- Fallback keys improve cache hit rates when lockfiles change slightly.
- Data restored from a fallback must be verified and updated by the tool against current dependencies.
- Avoid overly broad fallbacks for build outputs or data strongly tied to compiler, platform, or configuration.

A fallback key is a way to find starting data, not proof that restored data is already valid.

### 5.2. Versioning Caches

When cache layout changes, include a cache schema version in the key to prevent reading old data under a new format. This helps when upgrading toolchains, changing packaging methods, or switching OSes.

Do not cling to old caches at all costs. Caches can be purged and rebuilt. A controlled cache miss is usually cheaper than feeding stale, malformed data that causes hard-to-diagnose failures.

## 6. Caching Build Outputs and Computation Results

Beyond downloaded dependencies, some tools can cache build outputs or executed tasks. When inputs are unchanged, the tool can skip work and reuse outputs.

Examples:

- Gradle build cache.
- Compiler caches.
- Bundler or transpiler caches.
- Static analysis tool caches.
- Remote caches for monorepos or distributed build systems.

### 6.1. Conditions for Reusing Build Outputs

Build outputs should only be reused when the tool can track inputs and environment accurately enough. Inputs may include sources, dependencies, compilers, build flags, environment variables, generated code, and the OS.

Key principles:

- Prefer caching mechanisms that understand build tool tasks and inputs.
- Declare task inputs and outputs completely.
- Avoid tasks depending on current time, machine state, or undeclared files.
- Never write non-deterministic data to a shared cache.
- Use separate namespaces or keys for different environments.
- Maintain a clean build path to cross-check when cache corruption is suspected.

If a build task reads an environment variable not declared as an input, the cache may return outputs produced under a different configuration. In that case, the bug is not in cache storage, but in the build failing to declare every factor affecting outputs.

### 6.2. Caching Does Not Replace Testing

A cache hit only shows that data was found for a key. It does not prove new source code was tested or that results remain valid.

Pipelines must still run required test steps and record results for the current commit. If caching skips a task, the build tool must have a mechanism proving corresponding inputs did not change and the task output is validly reusable.

## 7. Artifacts as Deliverable Outputs

Artifacts must be managed as outputs with an explicit identity. When a build job produces an application package, the test or deploy job must receive that exact package rather than rebuilding from source in a different environment.

A release artifact should carry these attributes:

- Identifiable name and version.
- Commit SHA or source revision that produced it.
- Pipeline run ID and build timestamp.
- Versions of key runtimes, compilers, and build tools.
- Digest or checksum to verify contents.
- Dependency metadata or SBOM if required by process.
- Storage location, read/write permissions, and retention policy.
- Signature or provenance if origin verification is needed.

Artifacts should be immutable once published. If contents change, create a new artifact with a new identity. Never overwrite an existing release file with different contents under the same version.

### 7.1. Intermediate Artifacts and Release Artifacts

Not every file produced in a job needs long-term retention. Distinguish:

- **Intermediate artifacts:** files passed between jobs in the same pipeline, such as a binary for running integration tests.
- **Evidence artifacts:** test reports, coverage reports, selected logs, or scan results.
- **Release artifacts:** application packages or images to be promoted and deployed.
- **Release metadata:** manifests, SBOMs, provenance, signatures, and linkage records.

Intermediate artifacts can have shorter retention than release artifacts. Test reports may need retention per audit or investigation policies. Release artifacts must remain available long enough to support deployments, rollbacks, and supported environment reproduction.

### 7.2. Artifact Stores and Package Registries

A pipeline artifact store typically holds outputs of a single run for downstream jobs or user downloads. A package registry or container registry stores versioned packages/images and can serve multiple pipelines, environments, or teams.

Do not assume both places share the same policy:

| Storage | Goal | Example |
|---|---|---|
| CI artifact store | Handoff between jobs and storing pipeline results | JAR, test report, build bundle |
| Package registry | Distributing versioned packages | Maven package, npm package, NuGet |
| Container registry | Distributing container images | Image identified by tag and digest |
| Remote build cache | Reusing build outputs | Task output or compiler cache |

A package may be uploaded to an artifact store for testing, then published to a package registry once release criteria pass. Keep a link between the original artifact and published package, such as via digest and metadata.

## 8. Passing Artifacts Between Jobs

In multi-job pipelines, each job may run on a different runner. Local filesystems are usually not shared and should not be assumed to persist. Therefore, artifacts must be uploaded by the producing job and downloaded by dependent jobs.

Basic flow:

~~~mermaid
flowchart TD
    A["Checkout source"] --> B["Build"]
    B --> C["Create package"]
    C --> D["Upload artifact"]
    D --> E["Test job downloads artifact"]
    E --> F["Integration / acceptance tests"]
    F --> G{"Checks pass?"}
    G -- "No" --> H["Keep reports, halt release"]
    G -- "Yes" --> I["Deploy job downloads exact artifact"]
    I --> J["Deploy to environment"]
    J --> K["Verify version and digest"]
~~~

Steps to define:

1. The build job produces the artifact from a specific commit.
2. The pipeline verifies file existence, size, and valid structure.
3. The job uploads the artifact to managed storage.
4. The test job downloads the artifact matching the exact pipeline run or recorded identifier.
5. The deploy job downloads only an artifact that passed all required gates.
6. After deployment, the system verifies the running version or digest.

Do not pass files by relying on a previous runner's workspace directory. If jobs execute on different machines, local files will not exist. Use the platform's artifact handoff mechanism or a controlled repository.

### 8.1. Avoid Rebuilding in Every Job

Suppose the test job rebuilds the application and the deploy job rebuilds it too. Even from the same commit, results can differ due to dependencies, toolchains, environment variables, timestamps, or runner configuration.

For release workflows, prefer:

- Build one artifact from defined inputs.
- Test that exact artifact.
- Promote that exact artifact across environments.
- Verify the digest at every handoff point.

This minimizes discrepancies between what was tested and what gets deployed. Some projects may require separate builds per platform or architecture, yet each variant must still have its own identity, metadata, and evidence.

## 9. Ensuring Artifact Integrity and Origin

Artifacts can be corrupted in transit, overwritten, or replaced by an untrusted source. Therefore, both content and origin must be verified.

### 9.1. Digests and Checksums

After producing an artifact, the pipeline can compute a SHA-256 hash or use the digest provided by a registry. When downloading the artifact in a downstream job, recompute or verify the digest to ensure contents match.

A digest identifies exact byte contents. Comparing only filenames or version tags may fail to detect altered contents under the same name.

### 9.2. Provenance and Signatures

For systems requiring high assurance, add:

- Provenance describing source, builder, and artifact creation workflow.
- Digital signatures verifying the artifact was built or released by a trusted identity.
- SBOMs describing software components inside the artifact.
- Attestations or test evidence bound to the digest.

These mechanisms must integrate with builder identity and verification policies. A valid signature from an unauthorized identity does not prove an artifact is trustworthy.

### 9.3. Never Put Secrets into Artifacts

Artifacts can be shared across multiple jobs or users. Never package tokens, private keys, secret `.env` files, or sensitive data inside artifacts. Environment configs and secrets should be supplied at deployment or application startup via controlled mechanisms.

If an artifact is found to contain secrets, treat it as a credential leak incident: revoke or rotate credentials, identify where the artifact was downloaded, and produce a clean release.

## 10. Securing Caches and Preventing Cache Poisoning

Caches can be written by one run and restored by another. If an untrusted write source can modify a shared cache, trusted jobs may consume poisoned data.

Common risks:

- Pull requests from forks writing into a cache used by the main branch.
- Overly broad cache keys causing different branches or environments to share data.
- Caches containing replaced scripts or binaries.
- Stale caches restoring outdated dependencies.
- Caches accidentally storing secrets, tokens, or sensitive config files.
- Caches downloaded from external sources without verification.

### 10.1. Partitioning Caches by Trust Boundary

Define who may write to and read from caches:

- Caches from untrusted PRs must never serve as write sources for release pipelines.
- Main branch caches can have their own isolated scope.
- Writable build caches should be scoped by repository, branch, or trust level.
- Caches holding sensitive data must be isolated or excluded from shared caches.
- Never share caches between environments with different privilege levels without risk assessment.

Specific behavior depends on the CI/CD platform. Some platforms automatically scope caches by branch or ref; others allow broader sharing. Verify actual platform behavior instead of assuming automatic isolation.

### 10.2. Caches Are Not Secret Storage

Do not cache an entire `HOME` directory or workspace if credentials reside there. Select exact paths containing regenerable data. If accessing the cache itself requires authentication, supply credentials separately via a secret manager, never inside cached contents.

### 10.3. Suspected Cache Poisoning Response

Actions to take:

1. Stop using the affected cache key or namespace.
2. Purge the cache within the affected scope.
3. Run clean builds from a trusted dependency registry.
4. Inspect dependency checksums, signatures, and sources.
5. Identify which job or identity wrote the cache.
6. Audit artifacts built during the suspected window.
7. Rebuild artifacts and preserve investigation evidence.

Do not simply clear the cache and resume releasing without identifying which artifacts were built from the suspect cache.

## 11. Retention and Cleanup Policies

Caches and artifacts require different retention policies.

**Caches** can have short TTLs or be evicted by storage quotas. When old caches are rarely used or no longer relevant, delete them to reclaim storage. Clearing a cache must never break the ability to build correctly.

**Artifacts** require retention aligned with output value:

- Temporary pull request artifacts can have short retention.
- Test reports can be retained according to review and investigation needs.
- Release artifacts must be kept for the supported version lifetime and rollback policy.
- SBOMs, provenance, and approval evidence may need longer retention than temporary packages.
- Recovery-critical artifacts must be protected from routine cleanup jobs.

Establish rules to avoid accidentally deleting artifacts currently deployed or still supported. Cleanup should use metadata, release status, and retention policies, not file age alone.

## 12. Example Pipeline with Separate Cache and Artifacts

The example below illustrates how to organize jobs, caches, and artifacts conceptually. It is not syntax for a specific CI/CD platform:

~~~yaml
pipeline:
  build:
    steps:
      - checkout_source
      - restore_dependency_cache:
          key: os-runtime-toolchain-lockfile-hash
      - resolve_dependencies_from_trusted_registry
      - run_build
      - run_unit_tests
      - create_application_package
      - calculate_artifact_digest
      - upload_pipeline_artifact:
          name: application-package
          include:
            - application.jar
            - build-metadata.json

  integration_test:
    needs: [build]
    steps:
      - download_pipeline_artifact:
          name: application-package
      - verify_artifact_digest
      - run_integration_tests_on_downloaded_package
      - upload_test_report

  deploy:
    needs: [integration_test]
    condition: release_gates_pass
    steps:
      - download_pipeline_artifact:
          name: application-package
      - verify_artifact_digest
      - deploy_same_package
      - verify_running_version
~~~

Here, the dependency cache is restored to speed up resolution and library downloads. The application artifact is uploaded separately so the integration test and deploy jobs download the exact output of the build job. On a cache miss, the build can still fetch dependencies from the registry. If the application artifact is missing or its digest mismatches, dependent jobs must halt.

### 12.1. Java Project Example

With Gradle or Maven, consider:

- Cache Gradle/Maven dependency data to reduce package download time.
- Use dependency locking or explicit version declarations so resolution stays deterministic.
- Use the Gradle build cache when tasks declare inputs and outputs properly.
- Upload the built JAR/WAR as a pipeline artifact.
- Upload test and coverage reports as evidence artifacts.
- Publish approved packages to a Maven repository if they are distribution outputs.
- Deploy the exact tested JAR or image; do not rebuild inside the deploy job.

Exact cache paths and configuration depend on tool version, OS, and CI platform. Check the documentation for your specific tool before selecting directories or enabling remote caching.

## 13. Investigating Common Issues

| Symptom | Possible Cause | Investigation Direction |
|---|---|---|
| Cache hit yet build fails | Key misses inputs, stale cache, or build task under-declares inputs | Run clean build; compare key and task inputs |
| Continuous cache misses | Key changes too frequently, wrong cache scope, or short TTL | Check key components, frequency, and retention policy |
| Fast build yet deploy cannot find file | Relying on local workspace instead of artifact handoff | Check upload/download steps and artifact names |
| Test and deploy jobs run different builds | Each job rebuilds independently | Switch to passing the same artifact and verifying digests |
| Artifact overwritten | Mutable name/version or unlocked registry | Use unique versions, digests, and immutability policies |
| Artifact too large | Bundling intermediate files, caches, or unneeded data | Narrow file lists; separate reports from packages |
| Cache contains secrets | Cached entire workspace or `HOME` | Purge affected cache, revoke secrets, and restrict cache paths |
| PR pipeline pollutes release cache | Sharing cache write access across trust levels | Separate cache namespaces and read/write permissions |
| Artifact cannot be verified | Missing digest, metadata, or origin | Add appropriate manifest, checksum, and provenance |
| Artifact deleted before rollback needed | Retention ignores release lifecycle | Align retention policy with supported versions |

When investigating, determine whether the failure belongs to caching or artifacts. On a cache miss, try a clean build to confirm the pipeline can regenerate data. If an artifact is missing, has a mismatched digest, or lacks provenance, halt downstream steps and recover the valid output from a trusted pipeline run.

## 14. Sample Scenario: Build Once, Test and Deploy the Same Artifact

Suppose a team develops a Java service and wants shorter build times while ensuring production runs the exact build that was tested.

1. The pipeline receives a commit merged into the main branch.
2. The build job restores the dependency cache keyed by OS, JDK, Gradle wrapper, and lockfile.
3. On a cache miss, Gradle downloads dependencies from the configured repository. This may take longer, but does not change locked input identities.
4. The job runs unit tests, builds the JAR, and generates metadata containing commit SHA, pipeline run ID, and toolchain versions.
5. The pipeline computes a digest and uploads the JAR as a run artifact.
6. The integration test job runs on another runner, downloads the exact artifact, verifies the digest, and starts the service for testing.
7. Test reports are uploaded separately as evidence artifacts.
8. Once release gates pass, the deploy job downloads the exact tested JAR, verifies the digest again, and deploys to staging or production per policy.
9. The pipeline verifies the running version and records the artifact digest in the release record.
10. The cache can later expire without affecting the release stored in the artifact store or package registry.

In this scenario, caching reduces dependency download work. Artifacts ensure the build output is handed off accurately across jobs and environments. The two mechanisms complement each other, yet carry different lifecycles and trust requirements.

## 15. Practice Roadmap

Practice on a sample repository with these steps:

1. **Inventory pipeline data:** list dependencies, cache directories, build outputs, test reports, and release packages.
2. **Classify:** label each data type as source dependency, cache, intermediate artifact, evidence artifact, or release artifact.
3. **Lock dependencies:** add a lockfile or dependency locking mechanism, and pin runtime and build tool versions.
4. **Set up dependency caching:** pick proper package manager directories and construct keys from OS, toolchain, and lockfile.
5. **Test cache miss:** clear or change the cache key in a test environment and confirm the build still downloads dependencies and succeeds.
6. **Produce artifacts:** package the application, attach commit/run ID metadata, and compute a digest.
7. **Pass across jobs:** upload the artifact in the build job and download it in test and deploy jobs; do not rely on a prior runner's workspace.
8. **Verify integrity:** test with an invalid digest in a test environment and confirm the pipeline halts.
9. **Test security boundaries:** verify untrusted PRs cannot write to caches used by trusted releases or leak secrets into caches.
10. **Configure retention:** set distinct lifetimes for caches, temporary artifacts, reports, and release artifacts.
11. **Measure effectiveness:** compare dependency download times, cache hit rates, storage usage, artifact transfer times, and reproducible build rates.

### Completion Criteria

Learners can consider the exercise complete when they can demonstrate:

- Explaining why caches are speed optimizations while artifacts are deliverable outputs.
- Correctly classifying dependencies, caches, build outputs, and release artifacts.
- Designing cache keys reflecting inputs that affect compatibility.
- Proving the pipeline still succeeds on a cache miss.
- Uploading and downloading artifacts between independent jobs.
- Verifying artifacts with digests and metadata.
- Deploying the exact tested artifact across environments.
- Separating cache permissions by trust boundary and keeping secrets out of caches.
- Configuring distinct retention policies for caches, reports, and release artifacts.
- Investigating cache misses, cache poisoning, and missing or digest-mismatched artifacts.

## Conclusion

Caches and artifacts both support pipelines, but carry distinct responsibilities. Caches reuse regenerable data to save time; artifacts store outputs and evidence that must be handed off, tested, released, or traced. A cache can disappear and the pipeline must still run properly. An artifact must have an identity, be retained per policy, and be verified before use.

An effective CI/CD architecture manages dependencies with explicit versions, designs cache keys from actual inputs, isolates caches along trust boundaries, and transfers artifacts across jobs via controlled storage. By building once, then testing and deploying the same artifact, teams can accelerate pipelines while knowing exactly which output was verified and is running in the target environment.
