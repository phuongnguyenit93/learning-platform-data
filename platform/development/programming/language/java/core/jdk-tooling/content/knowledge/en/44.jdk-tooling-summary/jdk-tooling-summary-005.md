# Java Application Release Checklist

Releasing a Java application is the process of delivering a verified version from source code to users or a production environment. A reliable release must answer these questions: **which commit and version are being released, which JDK/toolchain built it, what checks did it pass, where is the final artifact located, how is the artifact verified, how is it deployed, and how is it rolled back if something goes wrong?**

This checklist applies to Java libraries, JAR applications, Spring Boot services, CLIs, application distributions, and containerized artifacts. Not every item applies to every project; mark non-applicable items as N/A with a reason in the release record.

A complete release requires an immutable artifact, a clear version, test results, dependency/SBOM records, checksums and signatures per policy, release notes, a deployment plan, and a rollback plan. You should not release simply because the build command exited with code 0.

## 1. Define Release Scope and Owner

Before building, record the release identification details:

- Name of the product, service, or library.
- Version to be released and version type: stable, release candidate, beta, or snapshot.
- Source repository and exact commit SHA.
- Corresponding Git tag; if required by the organization, use an annotated/signed tag.
- Release owner and approver.
- Target environment: staging, canary, production, or Maven repository.
- Issues, changes, and dependencies included in the version.
- Scope of changes to APIs, config, database schema, and runtime behavior.
- Release date, deployment window, and notification channels.

Use a consistent version across POM/Gradle, manifest, artifact filename, container tag, release notes, and deployment metadata. Do not build from a working tree with uncommitted changes and then record the release as if it came from a clean commit.

If using Semantic Versioning, distinguish:

- **MAJOR:** incompatible API/contract changes.
- **MINOR:** backward-compatible functionality additions.
- **PATCH:** backward-compatible bug fixes.
- **Pre-release:** e.g., 2.5.0-rc.1, not yet a stable release.

SemVer is a versioning convention and does not automatically guarantee binary compatibility. For Java libraries, verify public APIs and compatibility using tools/methods appropriate for your project policy.

## 2. Lock Source and Git State

Before running the release build:

```sh
git status --short
git rev-parse HEAD
git log -1 --oneline
git tag --list
```

Verify:

- The working tree is clean or all changes are intentionally committed.
- The commit belongs to the properly reviewed/merged branch.
- The pull request is approved and required checks have passed.
- The tag has not already been used for another artifact.
- No local files, generated files, or secrets were accidentally committed.
- Submodule/LFS content is checked out at the correct revision if the project uses them.
- Git metadata is recorded in the release record.

Create the tag according to your organization's process once the version is finalized. For example, creating an annotated tag:

```sh
git tag -a v2.5.0 -m "Release 2.5.0"
git show v2.5.0
```

Once a tag has been published and associated with a release artifact, do not move the tag to another commit. If a bug is discovered after release, create a new version/tag according to policy; preserve history for auditing.

## 3. Confirm JDK and Build Toolchain

The build must run with a project-approved JDK. Check the environment:

```sh
java --version
javac --version
jar --version
mvn --version
./gradlew --version
```

Not every command is needed in the same project; Maven projects use Maven Wrapper, and Gradle projects use Gradle Wrapper. Wrappers ensure CI and developers use the build tool version pinned in the repository.

Record:

- JDK vendor and version.
- Java release target.
- Maven/Gradle version.
- Build agent OS and architecture.
- Plugin/compiler versions.
- Enabled build flags and profiles.
- Dependency repository/mirror used.

### Java release target

Maven can declare:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Gradle Kotlin DSL can configure the toolchain and compiler release:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}
```

Replace 17 with the Java release supported by the product. The `--release` option helps the compiler enforce the language level, bytecode target, and APIs of the selected release. Setting only source/target without controlling the API can produce bytecode that runs on an older runtime but references newer APIs.

Ensure tests run on supported runtimes, not just on the JDK used to compile. If multiple Java releases are supported, test each release according to the published support matrix.

## 4. Lock Build and Dependencies

Builds should be as reproducible as possible. Before release:

- Use a reviewed Maven Wrapper or Gradle Wrapper.
- Pin plugin and dependency versions.
- Avoid dynamic versions such as `1.+` or `latest.release` in release builds.
- Enable dependency locking if the project needs to lock resolved versions.
- Enable Gradle dependency verification to verify checksums/signatures against reviewed metadata.
- Use organization-approved repositories; avoid unknown-source repositories.
- Inspect the dependency tree and transitive changes.
- Do not include SNAPSHOTs or mutable dependencies in a stable release unless an approved exception exists.
- Record the repository, version, and checksum of critical artifacts.

Some inspection commands:

```sh
mvn -B -ntp dependency:tree
./gradlew dependencies
```

Gradle can generate SHA-256 verification metadata:

```sh
./gradlew --write-verification-metadata sha256 help
```

Review the generated metadata before committing. Do not automatically trust a new checksum just because Gradle downloaded that dependency; verify the source and version before accepting.

With Maven, use a controlled repository manager, configure an appropriate checksum policy, and ensure release artifacts cannot be overwritten. SHA-1/MD5 checksums from legacy repositories do not replace signatures or SHA-256 verified against a trust policy.

## 5. Check Source, Code Quality, and API

Before release, complete the appropriate checks:

- Compile all source sets.
- Unit tests and integration tests.
- Contract/API and serialization tests if applicable.
- Database migration tests.
- Tests on supported runtimes/OSes.
- Static analysis and linting.
- Code formatting checks if required.
- Deprecated API and internal JDK API checks.
- Public API/binary compatibility checks for libraries.
- Review changes to concurrency, thread lifecycle, and shutdown.
- Check error handling, timeouts, retries, and resource cleanup.
- Confirm no tests were unintentionally skipped.

You can use:

```sh
mvn -B -ntp clean verify
./gradlew --no-daemon clean check
```

Maven `verify` runs preceding lifecycle phases, including compile, test, and package according to the project configuration. Gradle `check` runs configured verification tasks. Inspect task/test reports; do not rely solely on the last line of terminal output.

For Java applications, consider checking dependency/class references with `jdeps`:

```sh
jdeps --jdk-internals app.jar
jdeps --multi-release 17 --summary app.jar
```

Replace `app.jar` with the actual artifact. Results should be reviewed by module/dependency and target Java release; `jdeps` does not replace runtime testing.

## 6. Check Dependency Security and Licenses

Before releasing:

- Run a dependency vulnerability scan using an organization-approved tool.
- Evaluate CVEs based on exploitability and impact, not just score.
- Check licenses of direct and transitive dependencies.
- Check for unmaintained dependencies or unsupported versions.
- Run secret scanning on source, config, and artifacts.
- Verify no private keys, tokens, passwords, or credentials are in the repository/JAR/container.
- Review access permissions for build agents and signing services.
- Inspect container base images and OS packages if releasing an image.
- Document exceptions/risk acceptance with an owner and expiry if remediation is not yet possible.

A clean dependency scan at build time does not guarantee the artifact remains safe forever. Store scan results and monitor new advisories per operational policy.

## 7. Inspect the Final JAR or Distribution

Inspect the packaged artifact, because running code in an IDE does not prove the release artifact is built correctly.

For a JAR:

```sh
jar --list --file target/app.jar
unzip -p target/app.jar META-INF/MANIFEST.MF
```

Confirm:

- Artifact name and version are correct.
- `Main-Class` is correct if it is an executable JAR.
- Required resources are packaged.
- No development configuration files or secrets are included.
- No unexpected duplicate classes/resources exist.
- Dependencies are provided according to the intended model: thin JAR, manifest `Class-Path`, fat JAR, or distribution.
- `module-info.class` and module descriptor are correct if using JPMS.
- No temporary files, test fixtures, local paths, or unintended debug artifacts are included.

Run a smoke test using the artifact itself:

```sh
java -jar target/app.jar --version
```

The command above only applies if the application supports the `--version` option and the JAR contains all required dependencies. For a thin JAR or distribution, use the script/classpath released alongside the artifact.

Do not substitute Maven `exec:java`, Gradle `run`, or running classes from an IDE for artifact smoke tests. Those commands may use build outputs and dependency classpaths that differ from the published artifact.

## 8. Check Runtime and Deployment Configuration

Confirm before releasing:

- Minimum and maximum supported Java runtime versions.
- JVM options: heap, GC, encoding, timezone, and container memory if applicable.
- Required environment variables.
- External configuration files and config precedence order.
- Ports, bind addresses, DNS, and proxies.
- File permissions, service user, and writable directories.
- Certificates, truststore, keystore, and secret providers.
- Database/queue/cache endpoints and connection pools.
- Health, readiness, and liveness endpoints.
- Graceful shutdown, timeouts, and SIGTERM handling.
- Resource limits and autoscaling policies.

Do not bake production secrets into JARs, manifests, Dockerfiles, image layers, or release notes. Provide secrets via a secret manager or the deployment platform's credential mechanism.

Keep the artifact identical between staging and production whenever possible; inject environment configuration at deploy time. If separate builds per environment are unavoidable, document the reason and how differences are verified.

## 9. Database Migration and Backward Compatibility

If the release changes schema or data:

- Review migration SQL and execution order.
- Test migrations on a suitable data copy.
- Evaluate lock duration, storage impact, and execution time.
- Verify backward compatibility between old code and new schema.
- Determine whether the migration is safely idempotent/re-runnable.
- Determine how to handle a migration that fails mid-way.
- Back up and test recovery before high-risk changes.
- Have an expand-contract plan if multiple application versions will run concurrently.

A binary rollback does not automatically reverse a database migration. Design schemas so the previous code version continues to work during the transition period; destructive data migrations require a separate plan, backups, and approval.

## 10. Generate SBOM and Provenance

An SBOM (Software Bill of Materials) lists components/dependencies in an artifact, typically including name, version, package identifier, and license. Use SPDX or CycloneDX format according to organizational policy.

Before release:

- Generate the SBOM from actually resolved dependencies.
- Link the SBOM to the exact artifact version and checksum.
- Check for missing components or unknown versions.
- Store the SBOM alongside release metadata.
- Update the SBOM if the artifact changes after build.

Provenance records which source revision, builder, workflow, and parameters produced the artifact. For critical releases, store verifiable attestations rather than merely writing descriptive lines in release notes.

An SBOM does not prove an artifact was built securely; provenance alone does not prove code is free of vulnerabilities. Both types of metadata support inventory, auditing, and supply chain investigation.

## 11. Sign Artifacts and Generate Checksums

If release policy requires JAR signing, sign after packaging and after all artifact-modifying steps are complete.

Example signing with `jarsigner` using a securely managed keystore/alias:

```sh
jarsigner -keystore release-keystore.p12 -storetype PKCS12 target/app.jar release-key
jarsigner -verify -strict -verbose -certs target/app.jar
```

Do not put keystore passwords in source code, committed scripts, or command lines that may be captured in process logs. CI should retrieve credentials from a secret manager or use a signing service/workload identity. Restrict who can sign and audit every signing operation.

After signing, compute the checksum of the exact final file being released:

Linux:

```sh
sha256sum target/app.jar > target/app.jar.sha256
sha256sum --check target/app.jar.sha256
```

macOS:

```sh
shasum -a 256 target/app.jar
```

Windows PowerShell:

```powershell
Get-FileHash -Path .\target\app.jar -Algorithm SHA256
```

A checksum confirms bytes match a reference digest; it does not authenticate the publisher if both the file and digest come from a compromised source. When authenticity is required, sign the manifest/artifact and verify the certificate/identity against a trust policy.

If the JAR is signed, the checksum must be generated after the signing step. If the JAR is subsequently modified, both the checksum and signature must be regenerated.

## 12. Naming and Publishing Immutable Artifacts

A release should have stable naming and coordinates, for example:

```text
orders-service-2.5.0.jar
orders-service-2.5.0.jar.sha256
orders-service-2.5.0.jar.asc
orders-service-2.5.0-sbom.json
release-notes-2.5.0.md
```

Actual filenames depend on repository conventions. Ensure the artifact, checksum, signature, SBOM, and release notes all point to the same version/build.

Publishing principles:

- Publish to an approved repository/registry.
- Do not overwrite an already-published release version.
- Do not use `latest` as the sole identifier for production.
- Store artifacts by version/digest.
- Restrict upload and delete permissions.
- Enable audit logging and retention.
- Verify the artifact after upload by re-downloading it and checking its checksum/signature.
- Do not delete old releases while deployments may still need to roll back or dependencies still reference them.

With Maven, the `deploy` command publishes artifacts according to the distribution management/repository configuration. For example:

```sh
mvn -B -ntp deploy
```

With Gradle, use the publishing plugin and `publish` task configured for the target repository. For example:

```sh
./gradlew publish
```

Only run the publish step from an approved release pipeline.

## 13. Container Images (If Deployed via Docker/Kubernetes)

If the release includes a container image:

- Pin the base image by an approved version/digest.
- Use a non-root user if the application does not require elevated privileges.
- Do not put secrets in image layers or build arguments that may be persisted.
- Copy only the necessary artifacts into the final image.
- Inspect the image filesystem, exposed ports, user, and entrypoint.
- Scan OS packages and dependencies.
- Generate an SBOM for the image per process.
- Sign the image and record its digest.
- Deploy by digest when you need to guarantee the exact tested image is used.

Image tags can be moved; digests identify specific content. A container image digest differs from the checksum of the JAR inside the image. If both layers need verification, record both the artifact digest and the image digest.

## 14. Staging Testing and Release Approval

Before production, deploy the exact artifact intended for release to staging or an equivalent environment.

Verify:

- Application starts up and health/readiness checks succeed.
- Critical business flows work.
- Authentication/authorization works properly.
- Database migrations and dependency integrations succeed.
- Logs contain no unexpected errors or secrets.
- Metrics/traces show latency and resource usage within thresholds.
- TLS, certificates, DNS, proxies, and network policies are correct.
- Graceful shutdown and restart work properly.
- Appropriate load/performance tests have completed.
- Backup/restore and rollback procedures are confirmed when needed.

Record who approved production, the timestamp, artifact digest, and stop/abort conditions. If staging uses a different artifact than production, explain why and verify the differences.

## 15. Controlled Production Deployment

Choose a strategy suited to the architecture:

- **Rolling deployment:** replaces instances incrementally; requires compatibility between old and new versions during the transition.
- **Canary:** routes a small percentage of traffic to the new version and monitors before expanding.
- **Blue/green:** deploys a parallel new environment and then switches traffic.
- **Maintenance window:** used when migrations or incompatible changes require service downtime.

Before deploying:

- Verify the artifact digest matches the approved release.
- Verify signatures/provenance if required by policy.
- Confirm capacity and maintenance window.
- Check backups, migration plan, and rollback target.
- Prepare on-call personnel and dashboards.
- Define thresholds for automatic stop or rollback.

During deployment:

- Monitor error rates, latency, saturation, restarts, and health.
- Monitor database connections, queue lag, and dependency failures.
- Expand the rollout in stages.
- Stop if defined thresholds are exceeded; do not proceed merely because the deploy process reports success.

## 16. Post-Deploy Smoke Tests and Verification

After production receives the release:

- Verify the running version/commit on each instance.
- Verify health and readiness.
- Exercise critical business flows using test accounts/safe data.
- Check response codes, latency, and error rates.
- Check logs, traces, and alerts.
- Check connectivity to databases, caches, queues, and external services.
- Confirm background jobs, schedulers, and consumers are running.
- Verify configuration and secrets are loaded correctly.
- Confirm no unexpected old instances remain.
- Record the deployment timestamp, artifact digest, and smoke test results.

A health endpoint returning UP does not mean all business logic works. Run smoke tests for critical paths without creating real transactions or sending unintended real notifications.

## 17. Rollback Plan

Every production release needs rollback criteria defined before deployment.

Define:

- Rollback triggers: error rate, latency, crash loops, corrupted data, or business KPIs.
- Who has authority to decide.
- The latest stable artifact version/digest.
- How to route traffic back to the previous version.
- How to retain or roll back configuration.
- Whether database migrations are compatible with the previous version.
- How data created while running the new version will be handled.
- How to verify the system is stable after rollback.

Rolling back the application does not always mean rolling back the database. For destructive or data-transforming migrations, a forward fix or backup restore may be needed instead of running a reverse migration. Verify this before release.

Do not delete old artifacts immediately after deployment. Keep the previous version in the repository and ensure it can be re-downloaded when needed.

## 18. Release Notes and Operations Handoff

Release notes should state:

- Version and release date.
- Commit/tag or build identifier.
- New features and notable bug fixes.
- Breaking changes and deprecations.
- Config/environment variable changes.
- Database migrations and data impact.
- Dependency/JDK/toolchain changes.
- Known issues and workarounds.
- Artifact location, checksum/signature, and SBOM.
- Deploy, verify, and rollback instructions.
- Point of contact and incident reporting channels.

Operations handoff must include enough information to identify the version, check status, search logs by correlation ID, and execute a rollback within assigned permissions. Do not include secrets or sensitive data in release notes.

## 19. Post-Release Monitoring

During the post-release period, monitor:

- Error rates and new exceptions.
- p50/p95/p99 latency.
- CPU, heap, GC pauses, and thread counts.
- Connection pools, queue lag, and retries.
- Database slow queries and locks.
- Restarts, OOMs, and crashes.
- Security alerts and authentication failures.
- Key business metrics.
- User feedback and support tickets.

Set the monitoring window based on the release's risk level. If an issue is detected, correlate logs/traces with the release version and commit to isolate it quickly.

Once the release is stable:

- Close the change/release ticket.
- Archive QA results, approvals, and deployment records.
- Retain artifacts, SBOMs, signatures, checksums, and provenance per retention policy.
- Revoke temporary credentials or permissions.
- Delete temporary dumps/test data per policy.
- Update known issues and operational documentation.
- Hold a post-mortem/review if an incident or rollback occurred.

## 20. Common Release Issues

| Symptom | Cause | Resolution |
|---|---|---|
| Local build passes but CI fails | Different JDK/toolchain, env, or dependencies | Pin wrapper/toolchain and record build environment |
| JAR runs in IDE but fails on deploy | Artifact missing resources/dependencies or wrong manifest | Smoke test the exact packaged file |
| UnsupportedClassVersionError | Runtime is older than bytecode target | Use the right runtime or build with a lower release target |
| NoClassDefFoundError | Thin JAR missing runtime dependencies | Package a distribution/fat JAR or provide libs |
| Dependencies change between builds | Dynamic versions or dependency lock not used | Pin versions and review dependency locks |
| Checksum mismatch after upload | Corrupted file, wrong version, or wrong artifact uploaded | Re-download, verify source and digest |
| Signature verification fails | Artifact modified after signing or certificate/trust policy error | Sign after final packaging, check signer and chain |
| Publish overwrites old artifact | Repository allows release redeploy | Enable immutable release policy and access controls |
| Production missing config | Secrets/config not injected properly | Check deployment config and secret provider |
| Migration breaks old version | Schema change is not backward-compatible | Use expand-contract and test rollback |
| Health is UP but business logic fails | Health check is too shallow | Run business smoke tests and monitor telemetry |
| Rollback does not restore data | Assumed migration was reversible | Prepare backups/forward fix and data plan |
| Release cannot be traced to commit | Missing tag/build metadata/provenance | Record commit SHA, build ID, and artifact digest |

## 21. Consolidated Checklist by Phase

### Pre-build

- [ ] Release version, scope, and owner are finalized.
- [ ] Commit/branch/tag are correct and working tree is clean.
- [ ] Reviews and required CI checks have passed.
- [ ] JDK vendor/version, Java release, and build tool are pinned.
- [ ] Wrapper, plugin, and dependency versions are locked.
- [ ] Repository and dependency verification are checked.
- [ ] No secrets or local files exist in source.

### Build and testing

- [ ] Clean build succeeds.
- [ ] Unit/integration/contract tests pass.
- [ ] Static analysis/linting passes.
- [ ] Dependency vulnerability and license scans are reviewed.
- [ ] API/binary compatibility is checked if it is a library.
- [ ] Database migrations and backward compatibility are tested.
- [ ] Tests on target Java runtimes are complete.

### Artifact and supply chain

- [ ] JAR/distribution has the correct name/version.
- [ ] Manifest/Main-Class/resources/dependencies are verified.
- [ ] The final artifact itself has been smoke tested.
- [ ] No secrets, dev config, or extraneous files are present.
- [ ] SBOM and provenance are generated/stored per policy.
- [ ] Artifact is signed if required by policy.
- [ ] Checksum is generated after all artifact-modifying steps.
- [ ] Signature/checksum are verified.
- [ ] Artifact is published immutably and verified by re-downloading.

### Deployment and post-release

- [ ] Staging has passed and approval is recorded.
- [ ] Backups, migrations, rollout, and rollback are ready.
- [ ] Production artifact digest matches the release record.
- [ ] Production smoke tests have passed.
- [ ] Health, metrics, logs, traces, and business metrics are stable.
- [ ] Release notes and operations handoff are complete.
- [ ] Temporary credentials/permissions are revoked.
- [ ] Artifact, SBOM, signature, checksum, and audit records are stored.
- [ ] Ticket/change record is closed or moved to monitoring.

## 22. Sample Release Record

You can store a record for each release so others can trace it without relying on terminal history:

```text
Product: orders-service
Version: 2.5.0
Git tag: v2.5.0
Commit: <full-commit-sha>
JDK: <vendor-and-version>
Java release target: 17
Build tool: Gradle Wrapper <version>
Build result: PASS
Test result: PASS
Security/license review: PASS
Artifact: orders-service-2.5.0.jar
SHA-256: <64-hex-digest>
Signature: <signature-reference>
SBOM: <sbom-reference>
Provenance: <attestation-reference>
Repository: <artifact-repository-location>
Staging approval: <approver-and-time>
Production deployment: <deployment-id-and-time>
Smoke test: PASS
Rollback target: <previous-version-and-digest>
Release owner: <owner>
```

Replace sample values with actual information. Do not record passwords, tokens, private keys, or secret contents in the release record.

## 23. References

- Oracle Java SE 17 — java launcher: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java SE 17 — jar tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- Oracle Java SE 17 — jarsigner: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Oracle Java SE 17 — jdeps: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- Apache Maven — Lifecycle Reference: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven JAR Plugin: https://maven.apache.org/plugins/maven-jar-plugin/
- Gradle User Manual — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle User Manual — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Gradle User Manual — Application Plugin: https://docs.gradle.org/current/userguide/application_plugin.html
- CycloneDX Specification: https://cyclonedx.org/specification/overview/
- SPDX Specification: https://spdx.github.io/spdx-spec/
- SLSA — Supply-chain Levels for Software Artifacts: https://slsa.dev/

A good release is one that is traceable and verifiable: knowing the exact source commit, JDK/toolchain, test results, dependencies, artifact digest, and approver. Smoke test the exact final artifact, publish an immutable version, roll out incrementally with observability, and prepare a rollback plan before production receives traffic.
