# Choosing a Security Level for a Java Toolchain

## 1. What is a toolchain security level?

In toolchain design, the **security level** describes how strictly controls protect the entire process of acquiring the JDK, running build tools, downloading dependencies/plugins, executing build scripts, producing artifacts, and releasing software.

A toolchain does not consist of the JDK alone. It also includes Maven or Gradle, the Wrapper, plugins, transitive libraries, repositories, caches, IDEs, CI runners, secrets, and artifact signing systems. A single component that is replaced or executes malicious code can alter the build output and introduce unwanted code into the product.

This article uses four practical profiles: Basic, Standard, High, and Very High. This is a classification for selecting controls based on risk, **not four official security levels from Java SE, Oracle, or SLSA**. An organization can rename them or map them to its internal policies.

## 2. What are we protecting?

A Java build has multiple trust boundaries:

| Component | Risk if compromised |
|---|---|
| JDK/compiler | Compiling modified code, injecting unintended behavior |
| Maven/Gradle and Wrapper | Executing code before or during the build |
| Plugins, annotation processors | Running code with the build process's privileges |
| Dependencies and repositories | Introducing forged or vulnerable libraries into the application |
| Build scripts | Reading files, accessing the network, modifying artifacts, and exfiltrating secrets |
| CI runners and caches | Leaking credentials or poisoning subsequent builds |
| Signing keys and release credentials | Releasing forged artifacts under the organization's name |

Maven plugins, Gradle plugins, build scripts, and annotation processors are all executable code. Treat changes to a plugin or Wrapper like code changes with security impact.

## 3. Assess risk before choosing a level

Consider three factors:

- **Impact:** Does the toolchain only build lab exercises, internal applications, or production products with sensitive data?
- **Exposure:** Is it a private repository with a trusted team, a public repository, or does it accept pull requests from external contributors?
- **Privileges held by the build:** Does it only read source code, or does it have permissions to publish packages, deploy to production, access the cloud, or sign artifacts?

Choose the profile based on the highest risk among the three factors, not the average. A project with few users whose build job has permissions to sign and release to production still needs high-level controls.

## 4. Four practical security profiles

| Profile | Suitable scenarios | Key controls |
|---|---|---|
| Basic | Learning, experimentation, personal machines, no production secrets | JDK and build tools from clear sources, use Wrapper, HTTPS, version pinning, do not run untrusted files |
| Standard | Development teams, internal CI, typical applications | Wrapper checksum checks, dependency verification, plugin pinning, vulnerability scanning, least-privilege CI |
| High | Production products, public repositories, or accepting external contributions | Isolated runners, pinned actions, verified dependencies and releases, OIDC, artifact signing, provenance |
| Very High | Critical systems, finance, sensitive data, or audit requirements | Isolated and hardened builders, egress control, release approvals, protected signing keys, independently verifiable provenance |

The profiles accumulate controls. When moving from Standard to High, keep the existing version pinning, checksums, and dependency verification in place. Only raise the level when the risk requires it; there is no need to build a complex control system for a lab exercise with no sensitive access.

## 5. Foundational controls at every level

Regardless of which profile you choose, keep these principles:

1. Download the JDK and build tools from official distributions or sources over HTTPS.
2. Pin specific versions for the JDK, Maven/Gradle, plugins, and critical dependencies.
3. Use a Wrapper committed to the repository and verify its integrity.
4. Do not run build scripts from untrusted checkouts on machines holding credentials.
5. Do not place passwords, tokens, private keys, or certificates in source code, build files, or caches.
6. Use the minimum necessary OS account and permissions.
7. Apply security patches and address dependency alerts of appropriate severity.
8. Maintain a way to trace back the source, toolchain, and dependencies that produced a released artifact.

These measures form a baseline to strengthen for each profile.

## 6. Selecting and pinning the JDK

Choose a JDK from a vendor with an update policy, official download sources, published signatures or checksums, and a support schedule aligned with your product lifecycle.

Specify:

- Vendor and build distribution name.
- Java feature release and patch/update version.
- Operating system, architecture, and package type.
- Download source and checksum/signature verification method.
- Update schedule when security patches are released.

Do not use floating version names like `latest` in production builds. The same feature release can have multiple patch levels and vendor builds. Pin the exact build needed so builds are reproducible and investigable.

Check the actual JDK:

~~~bash
java --version
javac --version
java -XshowSettings:properties -version
~~~

On CI, log the selected JDK version and path. Configure the Java Toolchain for compile/test tasks so IDEs, developer machines, and runners use the same baseline.

## 7. Securing the Maven Wrapper

Maven Wrapper ensures every machine uses the project's exact Maven distribution. The Wrapper also downloads and executes binaries, so both the Wrapper JAR and the Maven distribution must be verified.

In `.mvn/wrapper/maven-wrapper.properties`, use two properties:

- `wrapperSha256Sum` to verify the `maven-wrapper.jar` file.
- `distributionSha256Sum` to verify the downloaded Maven distribution.

Obtain the SHA-256 from official Apache Maven sources or a repository mirror verified by your organization. Do not compute the checksum from the file you just downloaded and treat it as an independent trusted source.

Verification steps:

1. Review `mvnw`, `mvnw.cmd`, and `maven-wrapper.jar` in pull requests.
2. Pin the distribution URL to a specific Maven version over HTTPS.
3. Record the checksums of the Wrapper JAR and distribution.
4. When upgrading Maven, verify the new binaries and checksums before updating.
5. Use an internal repository manager if the organization needs to control artifact sources.

Do not run the Wrapper from an unfamiliar repository before reviewing these files. A replaced Wrapper can execute code before Maven even starts the build.

## 8. Securing the Gradle Wrapper

Gradle Wrapper also executes a binary stored in the repository and downloads a distribution from the configured URL. In `gradle/wrapper/gradle-wrapper.properties`:

- Pin `distributionUrl` to an exact version, using HTTPS and an official source or controlled mirror.
- Set `distributionSha256Sum` to the published SHA-256 for that exact distribution ZIP.
- Verify `gradle-wrapper.jar` with its official checksum or signature upon creation and on every version upgrade.

Example URL entry:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
~~~

Add the independent checksum for that exact ZIP before using it in a trusted environment. Gradle will fail the build if the downloaded checksum does not match the pinned value.

Before running the Wrapper from an unfamiliar checkout, read the properties, inspect the Wrapper JAR, and check `settings.gradle(.kts)`, `build.gradle(.kts)`, and `buildSrc/`. Opening a project in an IDE can also trigger Gradle sync and execute build logic.

## 9. Verifying dependencies and plugins in Gradle

Gradle supports **dependency verification** using checksums and signatures. When `gradle/verification-metadata.xml` is present, Gradle automatically checks artifacts downloaded by the dependency engine, including libraries, metadata, and plugins.

Generate initial metadata:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

If artifacts have trusted PGP signatures, you can generate both checksums and signatures:

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

Checksums verify that content has not changed; signatures verify that artifacts were signed by trusted keys. Use SHA-256 or SHA-512 for modern checksums. Do not use MD5 or SHA-1 as a new verification mechanism.

**Bootstrap warning:** the metadata generation command downloads dependencies from the current repositories and records their checksums/keys. If a repository is already compromised or a malicious dependency has been injected, the newly generated metadata can legitimize that very artifact. Review the diff, and verify official sources and keys of critical dependencies before committing the metadata file.

Gradle does not automatically verify changing dependencies such as SNAPSHOTs in this manner. Release builds should use immutable versions and avoid continuously changing dependencies.

## 10. Managing dependencies and plugins in Maven

With Maven, explicitly control dependencies, plugins, and repositories:

- Pin versions for Maven plugins in `pom.xml`; avoid unmanaged default versions.
- Avoid version ranges and SNAPSHOTs in release builds.
- Use `dependencyManagement` to centralize version management in multi-module projects.
- Inspect transitive dependencies with `mvn dependency:tree`.
- Use an organization-controlled repository manager/mirror if a unified download source is needed.
- Only allow HTTPS repositories and approved sources.
- Review changes to plugins, extensions, and annotation processors as executable code.

Inspect the dependency tree:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dverbose
~~~

Maven 3.9.x includes Plugin Validation to warn about certain configuration and plugin issues. You can increase verbosity when investigating:

~~~bash
mvn -Dmaven.plugin.validation=verbose verify
~~~

Plugin Validation helps detect plugin compatibility and configuration issues; it is not a malware scanner or an artifact signature verification mechanism.

## 11. Vulnerability scanning and SBOM generation

Verifying artifact origin and scanning for vulnerabilities are two different tasks:

- **Checksum/signature:** checks the integrity and signer identity of an artifact.
- **SCA:** finds dependencies with disclosed vulnerabilities.
- **SBOM:** lists the software components used to build or package a product.

OWASP Dependency-Check is an SCA tool that can identify dependencies and match them against public vulnerabilities. Results may have false positives, false negatives, or outdated data; review them before blocking a release.

For production releases:

1. Scan both direct and transitive dependencies.
2. Establish remediation policies based on severity, exploitability, and exposure.
3. Record exceptions with an assigned owner and review expiration date.
4. Generate an SBOM in an appropriate format such as CycloneDX or SPDX.
5. Store the SBOM alongside the artifacts and release metadata.

A dependency with no known CVEs can still be malicious or forged. SCA does not replace dependency verification.

## 12. Reviewing build scripts and plugins as executable code

Code in `pom.xml`, `settings.xml`, `build.gradle`, `settings.gradle`, `buildSrc`, Maven extensions, and plugins can execute during the build.

When reviewing toolchain changes, look for:

- New plugins or unexplained plugin version changes.
- Tasks running shells/processes, or downloading scripts or binaries from unfamiliar URLs.
- New repositories, unfamiliar mirrors, or HTTP URLs.
- Tasks reading environment variables, home directories, SSH keys, or credentials.
- Scripts modifying files outside the workspace or sending data over the network.
- Dependencies added to build logic that do not appear in the runtime dependency tree.

For projects outside the organization, inspect them before running `./gradlew`, `mvnw`, or opening the project in an IDE. Use an isolated container/VM if you cannot fully verify them yet.

## 13. Separating pull requests from releases

A secure pipeline should separate builds that test contributor code from release builds:

- **Untrusted pull requests:** run tests/linting with minimal read permissions; do not grant production secrets, signing keys, or deploy permissions.
- **Builds from protected branches:** only run after code review and branch protection policies.
- **Releases:** use dedicated jobs, environments with approval gates, scoped write permissions, and identified commit sources.
- **Signing/deploying:** separate from jobs running pull request code; only accept verified artifacts from trusted builds.

Do not use a single runner with production credentials for all event types. Do not allow artifacts/caches from untrusted builds to flow directly into releases without re-verification.

## 14. Limiting CI permissions and protecting secrets

Apply least privilege:

- Default tokens should be read-only if the build does not need write access.
- Grant package write or deploy permissions only to the specific job that needs them.
- Use per-environment service accounts instead of long-lived personal credentials.
- Do not print secrets to logs, command lines, or artifacts.
- Do not store secrets in Docker layers, caches, public build scans, or committed configuration files.
- Rotate credentials and revoke them immediately if a leak is suspected.

With GitHub Actions, permissions can be declared at the workflow/job level:

~~~yaml
permissions:
  contents: read
~~~

A job that needs to obtain an OIDC token to authenticate with a cloud provider can add `id-token: write` to that specific job. This permission only allows requesting the token; the cloud provider must still configure a trust policy restricting which repository, branch, environment, or workflow is allowed to receive credentials.

Prefer short-lived OIDC tokens over storing long-lived cloud access keys in GitHub Secrets when the cloud provider supports it.

## 15. Pinning GitHub Actions and controlling workflows

Third-party actions are executable dependencies in CI. GitHub recommends using workflow dependency lockfiles where supported; if not using a lockfile, pin actions to a verified full-length commit SHA from the upstream repository.

Do not treat a tag like `@v4` as an immutable version: tags can be moved. When upgrading an action, inspect its release, commits, changelog, and the permissions it requests.

Additionally:

- Set minimal `permissions` at the workflow and job levels.
- Restrict environment secrets by branch/tag and approval gates.
- Do not check out and execute untrusted code in a workflow with write permissions.
- Review reusable workflows and composite actions like dependencies.
- Keep runners updated and restrict who has permission to modify workflows.

A compromised runner can read secrets granted to the job, tamper with artifacts, and affect subsequent jobs if the environment is shared.

## 16. Isolating runners, workspaces, and caches

Runners execute build scripts and tests, so limit the blast radius:

- Use ephemeral runners for high-risk builds; destroy the environment after the job.
- Separate PR runners, trusted build runners, and signing/release runners.
- Run as a non-privileged user.
- Restrict network egress and only allow necessary repositories/services.
- Do not mount the home directory, Docker socket, or host credentials unless required.
- Scope caches by trust boundary; do not let untrusted PRs write to caches that trusted release jobs will restore.
- Do not reuse workspaces containing executables or secrets across unrelated projects.

Caches are only a performance optimization. When cache poisoning is suspected, discard the affected cache and rebuild from verified dependencies. Do not treat a cache hit as proof that an artifact is safe.

## 17. Signing artifacts and proving build provenance

For critical releases, sign artifacts after the build has been verified. Store signing keys in a key management service or HSM/KMS; do not place private keys in source code, runner images, or caches.

Store alongside the release:

- Hash of the released artifact.
- Source commit/tag and review status.
- JDK, Maven/Gradle, plugin, and dependency versions.
- SBOM and scan results.
- Workflow/runner identity and build timestamp.
- Signatures and build provenance/attestation, if available.

GitHub Actions supports artifact attestations to record provenance. SLSA defines assurance levels for the build supply chain. Provenance lets consumers see which source, builder, and process produced an artifact; signatures help detect tampering with provenance after creation.

## 18. Using SLSA as a maturity reference

SLSA Build Track v1.2 describes the following levels:

| Level | Meaning |
|---|---|
| Build L0 | No guarantees under the track |
| Build L1 | Provenance exists describing how the package was created |
| Build L2 | Provenance is signed and generated by a hosted build platform |
| Build L3 | Build platform is hardened to prevent tampering during the build |

SLSA is a reference framework for the supply chain; the four practical profiles in this article are not directly equivalent to SLSA levels. You can use SLSA to set targets for your build/release process and measure control gaps.

Do not claim to have achieved a SLSA level just because you generated a provenance file or enabled a CI feature. All requirements of the applicable track and specification version must be met.

## 19. Do not confuse toolchain security levels with Java Security Manager

Java Security Manager used to be the mechanism for controlling code permissions inside the JVM. It was deprecated for removal in JDK 17 and **permanently disabled in JDK 24**. It cannot be enabled at JVM startup, nor can a custom Security Manager be installed; there is no direct replacement in Java SE.

Therefore, do not try to set a toolchain security level by adding `-Djava.security.manager` or legacy policy files. To isolate untrusted build scripts/plugins, use OS and infrastructure controls:

- Containers or VMs with non-privileged users.
- Restricted filesystem and network namespaces/permissions.
- Network egress policies.
- Short-lived credentials scoped per job.
- Ephemeral runners and environment isolation.

Configuring TLS, truststores, keystores, and cryptographic algorithms for a Java application is a separate runtime/application security topic. They do not replace protecting the JDK, Wrapper, plugins, dependencies, and CI in the toolchain.

## 20. How to choose a profile by scenario

| Scenario | Starting profile | Reason |
|---|---|---|
| Java lab exercise on a laptop, no secrets | Basic | Low impact and low privileges |
| Internal application, CI only builds/tests | Standard | Shared dependencies and runners require verification |
| Public library accepting community pull requests | High | Builds receive untrusted code and carry supply-chain risk |
| Production backend with cloud deploy permissions | High | Credentials and artifacts directly impact production |
| Critical product or subject to audit requirements | Very High | Requires isolated builders, provenance, approvals, and signing controls |

When unsure, start at Standard for shared CI. Upgrade to High when builds process external code, hold release permissions, or handle critical secrets. Use Very High when the consequences of a forged artifact or compromised runner are severe.

## 21. Rollout roadmap

Roll out controls incrementally so the team can verify the impact:

1. Inventory current JDK, Maven/Gradle, Wrapper, plugins, repositories, and CI permissions.
2. Pin versions and verify checksums for the JDK/Wrapper.
3. Enable Gradle dependency verification or enforce dependency/repository controls in Maven.
4. Pin plugins/actions and review build logic changes.
5. Enable SCA, generate SBOMs, and establish a CVE remediation workflow.
6. Separate pull request, trusted build, signing, and deploy jobs.
7. Reduce token permissions, use OIDC where possible, and isolate runners/caches.
8. Sign artifacts, store provenance, and set approval gates for critical releases.
9. Periodically review wrappers, dependencies, actions, runner images, and signing policies.

After each step, measure build time, verification failure counts, alert volume, and maintenance effort. A good profile protects against the right risks while allowing the team to maintain stable builds.

## 22. Common implementation mistakes

### Pinning versions without checking checksums

Pinning a URL selects the right name/version, but does not verify the contents of the downloaded ZIP. Add checksums obtained from an independent official source.

### Generating verification metadata and committing immediately

Bootstrapping metadata can record already-compromised artifacts. Review checksums, signatures, keys, and download sources before trusting them.

### Scanning for CVEs while ignoring build plugins

Plugins and build logic are also executable dependencies. Include plugins in version control, reviews, and verification.

### Sharing a runner with deploy permissions for pull requests

Build scripts from PRs can read the runner's credentials. Separate runners and jobs by trust boundary, and never grant release secrets to untrusted events.

### Believing checksums prove the publisher

Checksums prove that content matches a trusted fingerprint; they do not by themselves verify who published it. Combine checksums with signatures and verify keys through an independent source.

### Using Security Manager as a sandbox on JDK 24

Security Manager is permanently disabled. Use containers/VMs, OS permissions, network policies, and credential scoping to isolate build processes.

### Raising security levels by adding as many scanners as possible

More tools do not automatically create assurance. Define what risk each tool detects, who acts on the results, and what conditions block a release.

## 23. Checklist for choosing and maintaining a security level

- [ ] Identified the impact if the JDK, a plugin, or a dependency is replaced.
- [ ] Assessed whether the repository accepts code from external contributors.
- [ ] Identified secrets, deploy permissions, and signing keys accessible to the build.
- [ ] Chosen the profile based on the highest risk.
- [ ] JDK and Maven/Gradle Wrapper use official sources, pinned versions, and checksums.
- [ ] Plugins, dependencies, and repositories are explicitly managed.
- [ ] Gradle dependency verification or an equivalent verification mechanism is reviewed.
- [ ] SCA and SBOM are in place for required releases.
- [ ] Untrusted pull requests have no release/signing permissions.
- [ ] Actions, workflows, runners, and caches are controlled by trust boundary.
- [ ] Secrets have least privilege, preferring short-lived/OIDC credentials.
- [ ] Released artifacts have appropriate hashes, signatures, and provenance.
- [ ] Security exceptions have an owner, expiration date, and review process.
- [ ] Periodic review schedule is in place for JDK patches, dependencies, plugins, actions, and runner images.

## 24. References

- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html): checking the Wrapper, distribution URLs, checksums, and untrusted checkouts.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksums, PGP signatures, verification metadata, and bootstrap limitations.
- [Gradle — Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html): distribution checksums and Wrapper verification when upgrading.
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/wrapper/): `wrapperSha256Sum` and `distributionSha256Sum`.
- [Apache Maven — Plugin Validation](https://maven.apache.org/guides/plugins/validation/): configuration warnings and plugin compatibility issues.
- [GitHub Actions — Secure Use](https://docs.github.com/en/actions/reference/security/secure-use): workflow dependencies, action pinning, least privilege, and handling untrusted code.
- [GitHub Actions — OIDC](https://docs.github.com/en/actions/reference/security/oidc): authenticating to cloud providers with short-lived federated identity tokens.
- [GitHub Actions — Artifact Attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations): generating and verifying artifact provenance.
- [SLSA v1.2 — Build Track](https://slsa.dev/spec/v1.2/build-track-basics): provenance and build platform assurance levels.
- [OWASP Dependency-Check](https://owasp.org/projects/dependency-check): analyzing dependencies to find disclosed vulnerabilities.
- [Oracle — Security Manager permanently disabled](https://docs.oracle.com/en/java/javase/24/migrate/migrating-jdk-8-later-jdk-releases.html): Security Manager changes in JDK 24.

Choose a security level based on the value of the artifacts, the sources of code that can enter the build, and the privileges the build holds. As these three factors increase, strengthen toolchain/dependency verification, isolate runners, reduce credential privileges, and add signatures and provenance for releases.
