# Downloading Dependencies from Controlled Sources

## 1. Why Does the Dependency Download Source Matter?

A build typically fetches many components that the team did not write directly: libraries, build plugins, compilers, base images, test tool packages, and transitive dependencies. Every component affects build output, safety, and version reproducibility.

If a pipeline downloads dependencies from multiple uncontrolled public sources, teams can run into problems:

- A package is replaced or a malicious version is published.
- A dependency with a name similar to an internal package is mistakenly picked up from a public registry.
- A registry becomes temporarily unreachable and causes builds to fail.
- Two build machines fetch different metadata or versions.
- A dependency is deleted or modified, making an old release impossible to reproduce.
- Repository credentials leak into logs, configuration files, or caches.
- A cache containing untrusted packages gets reused in a high-privilege pipeline.

Therefore, dependency management is not just declaring library names. Teams must control **source**, **identity**, **integrity**, **version**, **access permissions**, and **caching behavior**.

Within the scope of **DEVOPS_CI_CD_FUNDAMENTALS**, the goal is to build an automated, traceable build and test flow, manage artifacts and environments, protect secrets, and release under control. A trustworthy dependency source provides stable inputs to the pipeline, reduces supply chain risks, and aids investigation when a build fails.

## 2. Dependency Sources and the Role of a Repository Manager

Dependencies are typically distributed via package registries or repositories. For example:

- Maven Central for Java and JVM artifacts.
- npm registry for JavaScript packages.
- PyPI for Python packages.
- NuGet Gallery for .NET packages.
- Container registries for images.
- Internal repositories for libraries developed in-house by the organization.

Teams can download directly from public registries, but CI/CD environments need a unified control point. A repository manager such as Nexus Repository, JFrog Artifactory, or an equivalent registry service can sit between the pipeline and upstream sources.

A repository manager typically provides three repository types:

| Type | Role | Example |
|---|---|---|
| Proxy/remote | Fetches and caches packages from upstream according to policy | Maven Central or npm registry proxy |
| Hosted/local | Stores packages published internally by the organization | Internal libraries or release packages |
| Group/virtual | Aggregates multiple repositories under one endpoint | Combines internal packages and upstream proxies |

The pipeline can point to a single unified internal endpoint. The repository manager applies routing, authentication, caching, allowlists, and auditing behind the scenes.

A typical dependency download flow:

~~~mermaid
flowchart LR
    A["CI runner"] --> B["Internal repository"]
    B --> C{"Package already cached?"}
    C -- "Yes" --> D["Serve stored package"]
    C -- "No" --> E["Check policy and upstream"]
    E --> F["Allowed upstream registry"]
    F --> G["Verify and cache package"]
    G --> D
    D --> H["Build and test"]
    I["Internal package repository"] --> B
~~~

A repository manager helps control package flow, but does not automatically make every package safe. Teams must still verify versions, checksums or signatures, provenance, vulnerabilities, and usage policies.

### 2.1. Proxy Repository

A proxy repository receives package requests from clients, reaches out to upstream when needed, and stores contents according to a cache policy. Once cached, subsequent downloads can be served from the internal system.

Benefits:

- Reduces reliance on public registry availability.
- Speeds up repeated builds.
- Provides a central point to apply allowlists, scans, and audits.
- Reduces outbound requests from CI runners to the Internet.
- Retains previously used versions for an appropriate period.

Define which upstreams are permitted, how long caches live, which packages are blocked, and how to handle upstream changes or yanked/withdrawn packages.

### 2.2. Hosted Repository

A hosted repository stores packages owned or authorized for distribution by the organization. This is usually where internal libraries are published after building and testing.

Separate read and write permissions. Standard application CI jobs only need read access. Pipelines publishing new libraries need write access scoped to the exact repository and namespace. Do not grant publish credentials to every build job.

### 2.3. Group or Virtual Repository

A group repository provides a single URL for multiple sources. It prevents projects from having to declare numerous endpoints and lets administrators adjust backend sources with minimal impact on project configuration.

However, precedence order and handling of duplicate coordinates must be explicit. If an internal package shares coordinates with a public package, routing configuration can create dependency confusion. Reserve dedicated namespaces for internal packages and specify which repositories are authorized to serve those namespaces.

## 3. Designing Download Sources with Control Principles

A dependency source design should follow these principles:

1. **Maintain an allowlist of sources:** only use registries or repositories approved for each ecosystem.
2. **Prefer internal endpoints:** CI runners fetch packages through an organization-managed proxy or virtual repository.
3. **Separate internal and public packages:** internal namespaces must be strictly controlled.
4. **No arbitrary fallback:** when a trusted source is unreachable, pipelines must not fall back to uncontrolled registries.
5. **Least-privilege permissions:** build jobs get read-only access; publish jobs get write access limited to their scope.
6. **Use TLS and authentication:** protect transport connections and access identities.
7. **Keep audit trails:** log packages, versions, sources, timestamps, and identities that accessed or published them.
8. **Define retention policies:** keep packages needed for build reproduction and archival compliance.

### 3.1. Preventing Dependency Confusion

Dependency confusion occurs when a system picks a package from an unintended source due to identical or near-identical names, namespaces, or package coordinates.

For example, an internal application uses a package with Maven coordinates **com.company:payment-client**. If repository configuration allows resolving that package from both an internal repository and a public registry without strict precedence rules, a public package with the same coordinates could be selected in certain scenarios.

Mitigations:

- Use dedicated groupIds or namespaces for internal packages.
- Configure the repository manager so internal namespaces are served exclusively from corresponding hosted repositories.
- Prevent projects from arbitrarily adding public repositories when policy requires centralized sources.
- Use content filtering or exclusive repository mapping when supported by the package manager.
- Review changes to dependency coordinates and repositories.
- Monitor for newly appearing packages matching internal namespaces.

Do not rely solely on repository declaration order. Verify actual behavior of both the package manager and repository manager when multiple sources hold matching coordinates.

### 3.2. Distinguishing Release and Snapshot Sources

Officially released packages and in-development packages have different lifecycles.

In Maven, a release repository typically stores immutable versions like **2.3.1**; a snapshot repository stores mutable development versions like **2.4.0-SNAPSHOT**. Production pipelines should not pull snapshots arbitrarily because contents can change between two builds even though coordinates look identical.

Separating repositories enables:

- Granting separate publish permissions.
- Applying different retention policies.
- Enforcing different verification policies.
- Preventing experimental dependencies from entering official release streams.
- Easier investigation when a snapshot package causes a failure.

## 4. Verifying Package Identity and Integrity

Source control answers where a package came from. Integrity verification answers whether the received contents match what was published.

### 4.1. Checksums

A checksum is a hash value computed from file contents, typically using SHA-256 or an equivalent strong algorithm. Clients can recompute the checksum after downloading and compare it against a reference value.

Checksums help detect:

- File corruption during transit or storage.
- Package contents mismatching published metadata.
- Certain cases of unexpected package replacement.

A checksum is only valuable when the source providing the checksum is trustworthy. If an attacker replaces both the package and the checksum at the same source, comparison can still pass. For critical packages, combine digital signatures, provenance, or independent reference sources.

### 4.2. Digital Signatures

Digital signatures allow verifying that a package or metadata was signed by the corresponding key. Teams must know:

- Who or which system is authorized to sign.
- How public keys are distributed and trusted.
- How revoked or rotated keys are handled.
- Whether signatures are checked at download time, publish time, or pre-release.
- Where verification results are stored.

Do not accept a signature merely because a signature file accompanies the package. The pipeline must verify that the signing key belongs to a trusted set and that the algorithm/policy meets requirements.

### 4.3. Provenance and SBOM

Provenance describes how a package or artifact was built: source repository, commit, pipeline, builder, build parameters, and related steps. An SBOM (Software Bill of Materials) lists the software components inside a product.

These layers complement one another:

- Checksums identify file contents.
- Signatures verify the signer's identity.
- Provenance explains origin and creation process.
- SBOM shows which dependencies a product contains.

When a vulnerability alert hits a library, the SBOM identifies which product versions are affected. Provenance traces back to the build and source code that produced that artifact.

## 5. Pinning Versions and Locking Dependencies

A dependency declared with a version range or mutable tag can produce different results at different build times.

For example, a declaration allowing any version from **1.4** upward might resolve **1.4.3** today and **1.8.0** later. The newer version may alter APIs, behavior, or transitive dependencies.

To improve reproducibility:

- Pin direct dependency versions and critical plugin versions.
- Use lockfiles or dependency locking to record resolved versions.
- Control toolchain and package manager versions.
- Avoid **latest**, dynamic versions, and unnecessary version ranges in releases.
- Record repositories and checksums or verification metadata.
- Review lockfile changes just like source code changes.

Pinning versions does not mean keeping old dependencies forever. Teams need an intentional update workflow: propose new versions, run tests, scan for vulnerabilities, review changes, and re-release artifacts.

### 5.1. Maven

In Maven, a dependency is identified by groupId, artifactId, version, and optionally classifier/type. Release dependencies should declare explicit versions. Avoid LATEST, RELEASE, or version ranges in builds requiring reproducibility.

Maven can configure mirrors in **settings.xml** to route repository requests through an internal endpoint.

~~~xml
<settings>
  <mirrors>
    <mirror>
      <id>company-maven</id>
      <mirrorOf>*</mirrorOf>
      <url>https://packages.example.invalid/repository/maven-public/</url>
    </mirror>
  </mirrors>

  <servers>
    <server>
      <id>company-maven</id>
      <username>INJECTED_AT_RUNTIME</username>
      <password>INJECTED_AT_RUNTIME</password>
    </server>
  </servers>
</settings>
~~~

In this example, the URL uses an illustrative domain. Credentials are injected into a temporary settings file from the CI secret manager; do not commit tokens to the repository. The ID in the `servers` section must match the mirror ID so Maven finds the right credentials. Temporary files must have restricted read permissions and be deleted once the job finishes.

A mirror applies to all repositories when `mirrorOf` is configured for a centralized download policy. This is only suitable when the internal endpoint is configured to serve all required repositories. Any exceptions must be explicitly declared and reviewed.

Maven can be instructed to fail when repository checksums mismatch or are missing per policy:

~~~xml
<releases>
  <checksumPolicy>fail</checksumPolicy>
</releases>
~~~

Checksum policies only verify values supplied by the repository. They do not replace signature or provenance verification. With centralized mirror configurations, teams should verify how Maven applies repository policies in real projects and avoid declaring out-of-policy URLs in individual POMs.

### 5.2. Gradle

Gradle allows centralized repository declarations in **settings.gradle** and prevents projects from adding other sources on their own.

Groovy DSL example:

~~~groovy
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        maven {
            name = "companyMirror"
            url = uri("https://packages.example.invalid/repository/gradle-public/")

            credentials {
                username = providers.environmentVariable("MAVEN_REPO_USER").orNull
                password = providers.environmentVariable("MAVEN_REPO_TOKEN").orNull
            }
        }
    }
}
~~~

`FAIL_ON_PROJECT_REPOS` makes Gradle fail if a project declares its own repositories, keeping dependency sources in a single managed location. Credentials exist only in the build environment and must be granted least-privilege read access.

Gradle supports dependency locking to record resolved versions. Locking can be enabled in the appropriate configuration:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Then generate or update the lock state with an intentional run, review changed lockfiles, and commit them with source code. Understand which configurations are locked and how configuration resolution behaves so build or plugin dependencies are not overlooked.

Gradle dependency verification can store trusted checksums and signatures in **gradle/verification-metadata.xml**. Example of generating initial metadata:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

Generated metadata must be reviewed before committing. Do not blindly trust every checksum simply because the generation command downloaded the package successfully; for critical dependencies, cross-check trusted sources and signatures before accepting initial values.

### 5.3. npm and Python

For npm, configure an internal registry in **.npmrc** and use a lockfile such as **package-lock.json** to record versions and integrity metadata.

~~~ini
registry=https://packages.example.invalid/repository/npm-public/
@company:registry=https://packages.example.invalid/repository/npm-internal/
//packages.example.invalid/repository/npm-public/:_authToken=${NPM_READ_TOKEN}
always-auth=true
~~~

The token in the example is an environment variable provided by CI. The `.npmrc` file can be committed if it only contains URLs and variable references, but never commit actual token values. Ensure internal scope rules cannot be overridden by user-level configuration or another installation step.

For Python, configure `index-url` or `extra-index-url` to point to an internal package index. Exercise particular caution when combining multiple indexes: pip does not treat one index as an unconditionally safe preferred source for every package in every case. Use a repository proxy with clear namespaces and policies, version pinning, hash-checking mode, or an appropriate locking tool. Do not use `trusted-host` as a shortcut to fix TLS errors because it weakens connection verification.

## 6. Credentials and Repository Access Permissions

CI runners need credentials to read private packages or publish artifacts. These credentials must be treated as secrets and scoped appropriately.

Principles:

- Use read-only tokens for standard build jobs.
- Use separate write tokens for publish jobs.
- Separate credentials by environment or repository when needed.
- Prefer short-lived tokens or workload identity if supported by the platform.
- Do not pass tokens on the command line where they could appear in process listings or logs.
- Do not print settings file contents containing secrets to logs.
- Do not cache credential files in the workspace or shared caches.
- Revoke and rotate tokens if exposure is suspected.
- Restrict IPs, repositories, or namespaces if supported by the service.

A pull request from a fork is untrusted code. Do not expose internal package read secrets or publish credentials to jobs running that code without clear safeguards. Run checks that do not need secrets first, and grant permissions only in a separate job after changes are reviewed and satisfy policy.

## 7. Dependency Caching: Speeds Up Builds Without Replacing Source Control

Caching retains downloaded packages so subsequent builds do not need to re-download them. Caching can exist at multiple layers:

1. Local package manager cache on the runner.
2. Distributed cache provided by the CI platform.
3. Cache inside the repository manager or proxy.
4. Build tool cache such as Gradle or Maven caches.
5. Image layer cache of the container builder.

These layers serve different purposes. The repository manager controls sources and stores shared packages. CI caching reduces execution time across runs. Local caching helps repeated builds on the same runner. Do not confuse caches with a release artifact repository.

### 7.1. Choosing Cache Keys

Cache keys should reflect inputs that determine cache contents. For dependencies, common components include:

- Runner OS and architecture.
- JDK or runtime version.
- Package manager version.
- Lockfile or dependency declaration file.
- Repository configuration affecting download sources.
- Build tool or wrapper version.

For example, a Gradle cache can key on OS, JDK, and hashes of relevant Gradle files. When the lockfile or build script changes, a new key prevents reusing an incompatible cache.

Do not key caches solely by branch name if branches can use different dependencies. Likewise, do not share caches between jobs with different trust levels if cache contents could be written by untrusted code.

### 7.2. Cache Poisoning

Cache poisoning occurs when untrusted content is written into a cache and reused by another pipeline. Risk increases when:

- Jobs from external pull requests have write access to shared caches.
- Caches are shared between untrusted branches and release branches.
- Caches do not distinguish OS or toolchain versions.
- Cached contents are used without checksum verification.
- Credentials or sensitive configuration files are cached.

Mitigations:

- Partition caches by trust boundary.
- Restrict which jobs can write to caches.
- Use lockfiles and checksum/signature verification.
- Never cache secrets, tokens, or settings files containing credentials.
- Maintain a procedure to purge caches when contamination is suspected.
- Keep a clean-build path to verify independently of caches.

### 7.3. Caches Must Not Be the Single Source of Truth

A build succeeding thanks to a cache does not prove all dependencies can still be fetched from controlled sources. Maintain periodic clean builds or clean builds in the release pipeline to verify:

- Internal repositories still serve all required dependencies.
- Lockfiles and checksums are genuinely sufficient to reproduce the build.
- No dependency exists solely inside a runner's local cache.
- Required packages are still retained under retention policies.
- Source configurations have not drifted unexpectedly.

Caches can speed up day-to-day builds, but an independent verification mechanism and release reproducibility capability are still required.

## 8. Managing Metadata, Retention, and Availability

A repository manager does not only store package files. It also stores metadata, versions, checksum info, cached responses, and relationships between artifacts.

Define:

- How release metadata is kept stable.
- What TTL applies to snapshots or development packages.
- When dynamic metadata caches are refreshed.
- How yanked or vulnerable packages are handled.
- How long older versions are retained to reproduce releases.
- How repository storage, backups, and recovery are managed.

Do not delete a package merely because it is no longer the latest version. If a package was used to produce a production artifact, retaining it for an appropriate duration supports investigation and reproduction. Conversely, caches for snapshots or fast-moving metadata need suitable TTLs to avoid serving stale state too long.

The repository manager is also a critical pipeline service. Monitor:

- Request success and error rates.
- Package download latency.
- Cache hit ratio.
- Storage usage and growth rate.
- Authentication errors or access denials.
- Upstream errors and retry counts.
- Packages blocked by policy.

Multi-node setups or backups can be configured depending on platform capacity. However, availability must never be traded off by automatically falling back to uncontrolled sources.

## 9. Recording Dependency Provenance in Builds

To investigate a build, teams need to know the actual dependencies used, not just the initial declaration files.

Record:

- Package coordinates, version, and source repository.
- Checksum or digest.
- Package manager and build tool versions.
- Lockfile or dependency graph.
- Download timestamp and the build that consumed it.
- Vulnerability and license check results.
- Provenance of the final artifact.

With Gradle, export a dependency report or `dependencyInsight` to understand why a version was chosen. With Maven, `dependency:tree` reveals transitive dependencies and resolved versions. Attach reports to the commit and released artifact.

When a dependency has a vulnerability, teams can trace back:

1. Which package and version are affected?
2. Was that dependency pulled in directly or transitively?
3. Which artifacts or product versions contain it?
4. Which commit and pipeline produced the artifact?
5. Is a fix or verified replacement version available?
6. Which services need to be rebuilt and redeployed?

SBOMs and dependency graphs help answer these questions faster.

## 10. Quality Gates for Dependencies

Dependencies can be checked before merge, before publishing artifacts, or before deploying to production. Each stage has a distinct purpose.

| Stage | Appropriate Checks |
|---|---|
| Pull request | New packages, lockfile changes, licenses, version ranges, and repository sources |
| Build | Checksums, signatures, dependency resolution, and fetchability from permitted sources |
| Publish | Metadata, provenance, SBOM, and artifact digest |
| Release | Vulnerability policy, license policy, origin, and approved exceptions |
| Production | Verified artifact, no new dependency resolution during deployment |

Several rules can be automated:

- Reject packages from registries outside the allowlist.
- Reject version ranges or dynamic versions in release builds when policy requires pinning.
- Reject packages with mismatched checksums.
- Reject signatures not anchored in the trusted key set.
- Block packages with vulnerabilities exceeding policy thresholds without an approved exception.
- Disallow publishing internal packages from jobs lacking write permissions.
- Prevent production from downloading new dependencies at startup when dependencies can be packaged into the artifact beforehand.

Quality gates need clear rationale and owners. Low-severity license or vulnerability warnings may require review, whereas mismatched checksums or unauthorized package sources should fail the pipeline.

## 11. Example Controlled Dependency Flow for Java

Suppose a Java service uses Maven or Gradle, combining internal libraries and public packages.

Recommended flow:

1. A developer declares dependencies and updates the lockfile or verification metadata.
2. The pull request checks dependency diffs, licenses, vulnerabilities, and repository policies.
3. The CI runner receives a read-only credential from the secret manager.
4. Maven or Gradle accesses only the internal repository.
5. The repository manager fetches packages from allowlisted upstreams, verifies them per policy, and caches them.
6. The package manager verifies checksums or signatures according to configuration.
7. Build and tests execute on the resolved dependency graph.
8. The pipeline produces the artifact, SBOM, and provenance.
9. The artifact is stored in a controlled registry with a digest attached.
10. The release pipeline promotes the verified artifact without re-resolving dependencies.

A key point: dependency resolution must occur during the build stage. At deployment time, the application should receive a complete artifact with required dependencies already packaged. This prevents production environments from depending on external registry availability at startup.

## 12. Common Pitfalls When Downloading Dependencies

| Symptom | Risk | Mitigation |
|---|---|---|
| Every project declares its own registry | Hard to control sources and credentials | Standardize repositories via settings or conventions |
| Allowing fallback to public registries | May pick up wrong-namespace packages | Use centralized mirrors/proxies and allowlists |
| Using dynamic versions in releases | Build results drift over time | Pin versions and lock dependencies |
| Relying only on same-source checksums | Attackers can alter both package and checksum | Combine signatures, provenance, and trusted sources |
| Granting write tokens to all jobs | Amplifies blast radius if a runner is compromised | Separate read and publish permissions |
| Sharing caches between trusted and untrusted jobs | Risk of cache poisoning | Partition caches by trust boundary |
| Caching packages without clear retention | Loss of reproducibility or storage bloat | Set retention policies by package type |
| Ignoring transitive dependencies | Vulnerabilities can come from indirect packages | Store dependency graphs and scan everything |
| Installing dependencies at production startup | Increases network reliance and version drift | Package dependencies into the artifact |
| Bypassing TLS errors with trusted-host | Weakens connection verification | Configure CAs and certificates properly |

## 13. Checklist for Dependency Source Configuration

**Sources and repositories**

- [ ] Registries or repositories are approved and have owners.
- [ ] CI uses internal endpoints or controlled sources.
- [ ] Internal package namespaces are protected against dependency confusion.
- [ ] Releases and snapshots are separated according to policy.
- [ ] No fallback exists outside the allowlist.

**Identity and integrity**

- [ ] Connections use TLS and proper authentication.
- [ ] Checksums are verified.
- [ ] Signatures are checked if required by policy.
- [ ] Dependencies use explicit versions and lock states are reviewed.
- [ ] SBOMs or dependency reports are stored as required.
- [ ] Sources and provenance are traceable.

**Credentials and permissions**

- [ ] Build jobs use read-only tokens.
- [ ] Publish jobs have dedicated write credentials.
- [ ] Tokens are injected from a secret manager and never committed.
- [ ] Code from forks does not receive sensitive secrets.
- [ ] Credentials are not written to caches or logs.
- [ ] Token rotation and revocation procedures exist.

**Caching and reproducibility**

- [ ] Cache keys reflect lockfiles, toolchains, and platforms.
- [ ] Caches are isolated by trust boundary.
- [ ] Only authorized jobs write to caches.
- [ ] Periodic clean builds or release clean builds are performed.
- [ ] Repositories retain packages long enough to reproduce releases.
- [ ] Caches are not the sole source of dependencies.

## 14. Conclusion

Downloading dependencies from controlled sources is foundational for creating trustworthy, reproducible builds. Teams must agree on permitted repositories, govern internal namespaces, use proxies or virtual repositories when appropriate, verify checksums and signatures, pin versions, lock dependencies, and grant least-privilege credentials.

Caching speeds up builds, but is strictly an optimization layer. Package sources, integrity, and the dependency graph are what validate inputs. When every artifact can be traced back to its commit, packages, versions, repositories, and check results, pipelines can release faster while maintaining software supply chain control and auditability.
