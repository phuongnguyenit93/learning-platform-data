# Artifact Retention for Java Builds

## 1. What is artifact retention?

**Artifact retention** is the policy that defines where build artifacts are stored, how long they are kept, who is allowed to access them, when they are archived, and under what conditions they may be deleted.

In a Java project, artifacts may include:

- JAR, WAR, EAR, and release ZIP files.
- Maven POMs, Gradle module metadata, and checksum files.
- SBOMs, digital signatures, provenance attestations, and release manifests.
- Test reports, coverage reports, build logs, and build scans.
- Container images, native images, and auxiliary packages.
- Temporary build outputs from pull requests, nightly builds, or integration tests.

Good retention helps teams re-download the exact binary that was released, investigate incidents, meet audit requirements, recover from failures, and verify artifact provenance. The policy must also control storage capacity, cost, and the risk of retaining data for too long.

Retention is part of the software supply chain. If an artifact has been deployed in production, the team needs to know exactly which file was used and be able to retrieve that file along with its corresponding metadata.

## 2. Distinguishing artifacts, caches, backups, and archives

These four concepts serve different purposes:

| Type | Purpose | Examples |
|---|---|---|
| Build artifact | Output produced by a build. | JAR, WAR, SBOM, test report. |
| Cache | Speed up operations that can be regenerated. | Maven local repository, Gradle dependency cache. |
| Backup | Recover data after failure, accidental deletion, or disaster. | Repository manager backup, database, and blob store. |
| Archive | Long-term storage for lookup, audit, or release reproduction. | Release bundle, provenance, SBOM, and build manifest. |

A cache should not be treated as the storage location for released artifacts. Caches can be cleared or expire without losing the authoritative data source.

A backup also does not replace a retention policy. A backup may hold a copy of deleted data, but you still need to know which copy must be restored and when restoration is permitted.

An archive should contain enough data to identify and verify a release, not just a standalone JAR file without source information.

## 3. Classifying artifacts before setting retention periods

Each artifact type has its own lifecycle:

| Group | Examples | Retention approach |
|---|---|---|
| Pull request / feature build | Test JARs, test reports. | Short-term, automatic expiration. |
| Nightly / integration build | Binaries used for integration testing. | Keep long enough to investigate recent regressions. |
| Maven SNAPSHOT | 1.4.0-SNAPSHOT. | Limit by age and number of timestamped builds. |
| Release candidate | 1.4.0-rc.1. | Keep until release or until evaluation period ends. |
| Stable release | 1.4.0. | Keep according to support period and audit requirements. |
| LTS / regulated release | Releases with long-term support commitments. | Per contract, law, and legal hold. |
| Dependency cache | .m2, Gradle cache. | Deletable when downloadable/regenerable. |
| Release evidence | SBOM, signature, provenance, manifest. | Keep at least as long as or longer than the related artifact. |

Do not apply a single retention period to all groups. A test artifact used for only a few days has a different lifecycle from a JAR deployed to customers.

## 4. Building a retention policy

A policy needs to answer the following questions:

1. What category does the artifact belong to?
2. What is the authoritative storage location?
3. Is retention measured from build date, publish date, release date, or last download time?
4. Is a minimum number of recent versions kept?
5. Are there releases that must be protected because they are still supported?
6. Is there a legal hold, audit hold, or customer contract?
7. Who approves exceptions and who is permitted to delete?
8. After expiration, is the artifact deleted immediately, soft-deleted, or moved to an archive?
9. Are metadata and verification evidence deleted together with the binary?
10. How do you prove that cleanup ran properly?

The policy should be stored as a versioned configuration with an owner, effective date, and rationale. Do not rely on manual deletion commands without an audit trail.

## 5. Example retention matrix

The table below is an illustrative starting point for a typical Java team. These are not legal deadlines or mandatory regulations; organizations need to adjust them based on product lifecycle, contracts, and compliance requirements.

| Artifact class | Example retention period | Additional hold conditions |
|---|---:|---|
| Pull request build | 14 days | Keep longer if investigating an issue. |
| Nightly / integration | 60 days | Keep builds related to regressions or release candidates. |
| SNAPSHOT | 30 days | Keep at least the 5 most recent timestamped builds. |
| Release candidate | 90 days after release decision | Keep if an incident or audit is open. |
| Stable release | Support period + 2 years | Do not delete while still deployed. |
| LTS release | Per LTS policy/contract | Keep all release evidence as well. |
| Build logs | 90 days | Keep release logs and security-incident logs longer. |
| Maven/Gradle cache | 30 days unused | Can be regenerated from repositories. |
| SBOM/signature/provenance | At least as long as the artifact | Keep longer when needed for audit or investigation. |

These numbers only illustrate how to classify tiers. Explicitly specify units, starting timestamps, timezones, and how holidays/expirations are handled in the actual policy.

## 6. Choosing the timestamp for artifact age calculation

Retention can be based on several types of timestamps:

- **Created/uploaded time:** when the artifact was created or published.
- **Last downloaded time:** the last time a consumer downloaded the artifact.
- **Release date:** the date the release was approved.
- **End-of-support date:** the date product support ends.
- **Legal hold release date:** the date an authorized party allows lifting the hold.

Age-based policies suit temporary builds and snapshots. Usage-based policies help identify components that are no longer used. Release support policies need to be based on the product lifecycle.

Relying solely on last downloaded time can delete a release that is rarely downloaded yet still running in production. For stable releases, combine support status, deployment inventory, and release approval.

## 7. Maven releases and SNAPSHOTs have different lifecycles

Maven distinguishes between release versions and snapshot versions.

Release:

~~~xml
<version>1.4.2</version>
~~~

Snapshot:

~~~xml
<version>1.5.0-SNAPSHOT</version>
~~~

A release version represents a specific release. The authoritative repository should be configured to reject redeploying the same release coordinates once published.

Maven does not automatically guarantee that every repository server is immutable. The no-redeploy rule must be enforced by the repository manager or release pipeline.

A snapshot is a development build that can be published multiple times under the same base version. A remote repository can store timestamped files and use maven-metadata.xml to resolve 1.5.0-SNAPSHOT to the current deployment.

Therefore, snapshots can be cleaned up by age and number of versions to retain. Stable releases require longer retention and must be protected from snapshot cleanup.

## 8. Configuring Maven repositories for releases and snapshots

Example distributionManagement:

~~~xml
<distributionManagement>
  <repository>
    <id>internal-releases</id>
    <url>https://repo.example.com/repository/maven-releases/</url>
  </repository>
  <snapshotRepository>
    <id>internal-snapshots</id>
    <url>https://repo.example.com/repository/maven-snapshots/</url>
  </snapshotRepository>
</distributionManagement>
~~~

Credentials are configured in settings.xml matching the repository ID:

~~~xml
<settings>
  <servers>
    <server>
      <id>internal-releases</id>
      <username>BUILD_USER</username>
      <password>INJECTED_SECRET</password>
    </server>
    <server>
      <id>internal-snapshots</id>
      <username>BUILD_USER</username>
      <password>INJECTED_SECRET</password>
    </server>
  </servers>
</settings>
~~~

In CI, retrieve credentials from a secret manager or the pipeline's secret store. Do not commit passwords/tokens into POMs, settings.xml in the repository, or artifacts.

Use the Maven Wrapper and deploy with:

~~~bash
./mvnw -B -ntp clean deploy
~~~

Maven selects the release repository or snapshot repository based on the project's version. The repository manager needs to apply separate publish permissions, redeploy policies, and cleanup policies for each repository.

## 9. Maven repository layout and data to retain

The Maven repository layout turns coordinates into directory paths.

Example:

~~~text
com/acme/payment-service/1.4.2/
  payment-service-1.4.2.jar
  payment-service-1.4.2.pom
  payment-service-1.4.2.jar.sha1
  payment-service-1.4.2.jar.md5
  payment-service-1.4.2.pom.sha1
  payment-service-1.4.2.pom.md5
~~~

A repository may also contain detached .asc signatures, SHA-256 sidecars, and metadata files. Maven metadata maven-metadata.xml supports version discovery and snapshot resolution.

Do not delete POMs or metadata separately in a way that leaves artifacts existing but no longer resolvable via Maven coordinates. Do not manually delete timestamped snapshot files while ignoring the metadata managing snapshots.

A repository manager understands package layouts and relationships between assets; use the manager's cleanup policies rather than deleting files directly on blob storage.

## 10. Snapshot timestamps and cleanup

A remote snapshot can be stored with a timestamped filename:

~~~text
retention-demo-1.0.1-20261110.142015-3.jar
retention-demo-1.0.1-20261110.142015-3.pom
maven-metadata.xml
~~~

The base version remains 1.0.1-SNAPSHOT, while each specific deployment has a timestamp and counter.

When setting retention for snapshots, consider all of the following together:

- Keep snapshots for no longer than the specified number of days.
- Keep at least the N most recent deployments.
- Do not delete snapshots currently used by release candidates or integration tests.
- Provide a grace period after publishing the corresponding release.
- Ensure repository metadata remains valid after cleanup.

For example: keep the 5 newest snapshots and delete those older than 30 days, except snapshots marked with a hold. These numbers should match the team's build velocity and rollback/debugging needs.

## 11. Keeping releases immutable

A published stable release should have the following properties:

- Coordinates do not change.
- Binary bytes are not replaced.
- Digests are stored and verifiable.
- POM and release metadata are kept together with the binary.
- SBOM, signature, and provenance point to the exact digest.
- Release tag and source commit are recorded.

If a bug fix is needed, create a new version, such as 1.4.3, and publish all metadata anew. Do not replace the 1.4.2 JAR with a different binary while keeping the same version.

The repository manager should enable a disable-redeploy or release-immutability policy. Only the release service account should have publish permissions; delete permissions should be restricted separately.

## 12. Retention for GitHub Actions artifacts

GitHub Actions stores workflow artifacts and log files according to the retention policy of the repository/organization/enterprise.

According to current GitHub documentation:

- By default, artifacts and workflow logs are kept for 90 days.
- Public repositories can configure retention from 1 to 90 days.
- Private repositories can configure retention from 1 to 400 days.
- Organization or enterprise limits may be lower.
- Changing repository retention only applies to new artifacts/logs and does not automatically change the expiration of already created artifacts.

You can set a custom retention period for an artifact in a workflow:

~~~yaml
- name: Upload test output
  uses: actions/upload-artifact@v4
  with:
    name: pull-request-test-output
    path: |
      target/*.jar
      target/surefire-reports/
    retention-days: 14
~~~

retention-days must not exceed the limit of the repository, organization, or enterprise.

GitHub Actions workflow artifacts are suitable for sharing outputs between jobs or downloading test results. Release packages should be published to a package/repository registry with proper lifecycle and access policies. Do not use workflow artifact retention as the sole retention policy for released binaries.

## 13. Retaining logs, test reports, and build evidence

Build logs help explain why an artifact was produced. Test reports show which tests ran and what their results were.

For Java/Maven, evidence typically includes:

~~~text
target/
  surefire-reports/
  failsafe-reports/
  site/
  *.jar
  bom.json
  checksums.txt
~~~

There is no need to retain all temporary outputs of every build for the long term. Select the data needed for investigation and auditing:

- Release build logs.
- Unit/integration test reports.
- Test summaries and coverage reports.
- Dependency trees or resolved dependency manifests.
- JDK, Maven/Gradle, and plugin versions.
- Source commit, workflow run ID, and release tag.
- Digest of the final artifact.

If logs contain secrets or personal data, filter them before archiving. Do not store full environment dumps containing credentials just to preserve build evidence.

## 14. SBOMs, signatures, and provenance must follow the same artifact lifecycle

A release bundle may include:

~~~text
release/
  payment-service-1.4.2.jar
  payment-service-1.4.2.pom
  bom.cdx.json
  SHA256SUMS
  payment-service-1.4.2.sigstore.json
  provenance.intoto.jsonl
  release-manifest.json
~~~

The SBOM describes components; checksums identify bytes; signatures authenticate the signer; provenance explains the source and builder. This data should be kept alongside the release or stored in a metadata store linked by digest.

If a JAR is still used in production, its SBOM and provenance must also remain accessible. When investigating a dependency vulnerability, the team needs to know which specific release contains which component and which commit it was built from.

Do not generate a new SBOM and attach it to an old release if the dependency graph or artifact bytes have changed. For each release, determine the final artifact, generate the corresponding metadata, and store the digest.

## 15. Distinguishing dependency cache retention

The Maven local repository is typically located at:

~~~text
~/.m2/repository/
~~~

The Gradle dependency cache is typically located under:

~~~text
~/.gradle/caches/
~~~

These are caches to reduce download time for dependencies and plugins. They can be deleted or regenerated from repositories as long as the dependencies still exist and remain accessible.

Do not treat .m2/repository or .gradle/caches on a developer machine as the authoritative storage for releases. Releases should be published to a repository manager or package registry.

For proxy repositories, upstream caches can be cleaned up by usage/age. If an upstream removes a package or changes availability, retained caches can help older builds continue to resolve. Identify which dependencies must be mirrored internally to support long-term builds.

## 16. Retention policies in Sonatype Nexus Repository

Nexus Repository supports cleanup policies based on criteria such as:

- Component age.
- Component usage/last downloaded.
- Release type, such as RELEASES or PRELEASES.
- Retaining a number of latest versions when supported by the format, edition, and storage backend.

Cleanup policies are created, attached to repositories, and executed by cleanup tasks. Sonatype documentation notes that cleanup policies are not necessarily pre-configured; administrators must select appropriate policies and schedules.

Some Nexus versions soft-delete components first. Blob data is not reclaimed immediately; a compact blob store task is required to free physical space. Therefore, a component disappearing from the UI does not mean storage has immediately decreased.

For Maven, version retention is supported under specific editions/versions and PostgreSQL backends. Verify the actual deployment conditions before relying on retain N versions.

Before running cleanup in production, preview the list of affected components and check currently supported releases.

## 17. Retention policies in JFrog Artifactory

Artifactory provides cleanup policies for packages and build information.

A package cleanup policy can be based on:

- Packages older than.
- Packages not downloaded since.
- Property.
- Keep last N versions.

Policies can be applied by repository, package type, or stage depending on version and license capabilities.

Artifactory supports dry runs to generate a report of items scheduled for deletion. Review this report before enabling actual cleanup.

Distinguish between build-info retention and artifact retention. When deleting build records, depending on the Delete Build Artifacts option, related artifacts may also be deleted. Check this setting before running a policy.

Do not delete build metadata just because a build is old if the artifact is still in a release bundle, currently deployed, or needed for auditing.

## 18. Retention in object storage and archives

An organization may move old release evidence to object storage or an archive tier to reduce costs.

Example storage structure:

~~~text
java-releases/
  payment-service/
    1.4.2/
      artifact.jar
      artifact.pom
      bom.cdx.json
      SHA256SUMS
      provenance.intoto.jsonl
      release-manifest.json
~~~

Keep a manifest containing:

- Maven coordinates and filenames.
- SHA-256.
- Source commit and release tag.
- Publish time and expiration date.
- Retention class.
- SBOM/provenance reference.
- Legal hold status.
- Repository path or storage object version ID.

Object storage provides lifecycle transitions to move objects to cheaper storage tiers, but you must account for retrieval time, restore fees, and recovery time when production needs to re-download a release.

Do not delete repository indexes or metadata needed by consumers when only moving binaries to an archive. Maintain a catalog that can look up releases and their archive locations.

## 19. WORM retention and legal hold

For data that requires protection against modification/deletion, WORM (Write Once, Read Many) storage can be used.

Amazon S3 Object Lock supports retention periods and legal holds on object versions:

- Governance mode allows users with special bypass permissions to modify or delete under certain conditions.
- Compliance mode prevents deleting or shortening the retention period of an object version during the protection period, even by the root user.
- Legal holds have no fixed expiration date and only end when an authorized person removes the hold.
- Object Lock requires S3 Versioning to be enabled.

Compliance mode can be very difficult to reverse before the expiration date. Use it only when policies and legal requirements are confirmed. Governance mode is more suitable when a protection layer with a controlled exception process is needed.

Legal holds should be attached to specific object versions/digests. When an audit, dispute, or incident investigation occurs, place the related artifacts and evidence on hold before cleanup runs.

## 20. Retention does not replace backup and disaster recovery

A repository manager may retain artifacts for the proper duration and still lose data due to storage failure, misconfiguration, or account incidents.

A backup strategy should consider:

- Artifact binaries and POMs.
- Repository database and metadata.
- Blob/object storage.
- Build-info, SBOMs, signatures, and provenance.
- Repository configuration and cleanup policies.
- Encryption keys and access permissions required to restore.

Backups must be stored in an independent failure domain. If both artifacts and backups are deleted by a compromised credential or a faulty lifecycle policy, recovery will no longer be possible.

Backups must undergo periodic restore tests. Verify not only that files are recovered, but also that Maven/Gradle can resolve coordinates, digests match, and signatures/provenance can be verified.

## 21. Designing safe cleanup automation

A cleanup pipeline should include the following steps:

1. Compute the list of artifacts eligible for expiration.
2. Exclude artifacts currently deployed or in supported releases.
3. Exclude artifacts with a legal hold, audit hold, or exception.
4. Retain the minimum number of versions required by policy.
5. Generate a dry-run report.
6. Review the count, size, and list of affected releases.
7. Perform soft-delete or move to archive.
8. Wait for the grace period per policy.
9. Compact/garbage-collect storage if required by the repository manager.
10. Store the cleanup report and verify the state after execution.

Run on a small repository or project first before scaling out. If a cleanup task can delete both build-info and artifacts, check the impact using a dry run.

Cleanup should be idempotent: re-running it must not accidentally delete new artifacts or corrupt updated metadata. Do not run deletion commands based on wildcard paths without verifying package identity.

## 22. GitHub Actions example for retaining artifacts by period

A workflow can retain test outputs for 14 days:

~~~yaml
- name: Run tests
  run: ./mvnw -B -ntp clean verify

- name: Upload test evidence
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: test-evidence
    path: |
      target/surefire-reports/
      target/failsafe-reports/
    if-no-files-found: warn
    retention-days: 14
~~~

if: always() ensures reports are uploaded even when tests fail, as long as the runner can still execute the upload step.

Do not upload credentials, the entire workspace, or personal configuration files into artifacts. Name artifacts with the run ID or commit reference to avoid confusion between runs.

If release evidence needs long-term retention, publish it to a release repository/archive with a long-term policy and link it by digest. Short-lived workflow artifacts can serve debugging; the release repository holds the authoritative copy.

## 23. Identifying which artifacts are in use

A policy based on last download needs to know which consumers use the artifact.

You can collect:

- Repository access/download logs.
- Deployment manifests and container image digests.
- Maven dependency coordinates from release manifests.
- Service inventory and running versions.
- Release support status.
- Customer environments or branches pinning versions.

An artifact with no recent downloads may still be deployed from a cache, container image, or internal mirror. Therefore, last downloaded is only one signal.

Before deleting a stable release, cross-check against the deployment inventory, support matrix, and release manager. If usage cannot be determined, keep the artifact or move it to an archive until evidence is available.

## 24. Securing delete permissions and audit trails

Publish permissions and delete permissions should be separated.

A model you can use:

- Developer: publish snapshots and download artifacts.
- CI release service: publish stable releases via protected workflows.
- Repository administrator: configure retention policies.
- Cleanup service: delete only artifact groups permitted by policy.
- Auditor: read metadata and cleanup reports.
- Legal/compliance owner: request and remove legal holds following a process.

Record who created/modified policies, who ran cleanup, which policy version was applied, which items were deleted, and how much space was reclaimed.

For release repositories, require additional approval before deleting a published version. Do not grant WORM retention bypass permissions to regular CI accounts.

## 25. Common retention issues

| Symptom | Cause | Resolution |
|---|---|---|
| Workflow artifact disappears | retention-days or repository policy expired. | Check artifact expiry and publish long-lived releases to a registry. |
| Release JAR is overwritten | Repository allows redeploying the same version. | Enable immutable releases/disable redeploy. |
| Snapshot repository grows too large | No age/count cleanup. | Limit age and number of timestamped snapshots. |
| Maven fails to resolve snapshot | Snapshot metadata was deleted or out of sync. | Use repository manager cleanup instead of deleting files directly. |
| Artifact remains in UI but storage does not decrease | Repository manager soft-deletes first. | Run compaction/garbage collection per product documentation. |
| Cleanup deletes an in-use release | Policy relies only on age/last download. | Cross-check support/deployment inventory and add holds. |
| SBOM missing while JAR remains | Metadata has shorter retention than the artifact. | Keep SBOM/signature/provenance at least as long as the artifact. |
| Cannot recover after deletion | Backup missing blobs or metadata. | Back up both repository database and storage; test restores periodically. |
| Archive has files but cannot be found | No catalog/manifest. | Store coordinates, digest, source commit, and object path. |
| Legal hold does not protect the required build | Hold attached to the wrong object/version. | Identify by object version and digest before placing hold. |
| Storage does not decrease after cleanup | Blobs not compacted or lifecycle not run. | Check compaction tasks and storage reports. |
| Cleanup deletes dependency cache needed for old builds | Proxy cache cleaned up by usage. | Mirror critical dependencies or archive build inputs. |

## 26. Verifying Maven releases and snapshots in a local repository

An independent Java 17 project was deployed using Maven 3.9.12 and Maven Deploy Plugin 3.1.4 to a temporary file repository.

The first deployment used a release version:

~~~xml
<version>1.0.0</version>
~~~

Maven created release coordinates in the repository and the JAR file ran successfully:

~~~text
artifact-retention=ready
~~~

The project was then changed to:

~~~xml
<version>1.0.1-SNAPSHOT</version>
~~~

The snapshot deployment created timestamped files along with maven-metadata.xml. Release 1.0.0 still existed and remained runnable after the snapshot deployment.

This result confirms that Maven deploy and repository layout work in the test project. It does not prove that a production repository manager has enabled immutable releases or retention policies; those settings must be configured and verified on the actual repository.

## 27. Workflow for archiving a Java release

When a release is about to leave the hot repository:

1. Identify the release coordinates, digest, and source commit.
2. Check whether the release is still deployed or supported.
3. Collect JAR/WAR, POM, SBOM, checksums, signatures, and provenance.
4. Store test reports and build metadata according to policy.
5. Create a release manifest with publish date and expiration date.
6. Copy to the archive tier or immutable storage.
7. Verify the digest after copying.
8. Check signatures and provenance on the archived artifact.
9. Test resolving or downloading from the archive per the restore procedure.
10. Update the catalog so consumers know the new location.
11. Clean up the hot copy only after the archive has been verified.
12. Save an audit record of the transfer and cleanup.

If the repository manager supports promoting/copying releases, use that feature to preserve metadata and checksums. Do not copy only the JAR file and delete the Maven directory containing the POM/metadata.

## 28. Monitoring and auditing retention

You should monitor:

- Total storage by repository and artifact class.
- Number of releases, snapshots, and build artifacts by age.
- Number of artifacts approaching expiration.
- Cleanup run success/failure and item counts.
- Number of items under hold or exception.
- Blob store compaction and actual space reclaimed.
- Time to restore a release.
- Percentage of artifacts with digests, SBOMs, and provenance.
- Number of currently deployed artifacts nearing expiration.

Every quarter or release cycle, review whether the policy still fits the product lifecycle. Test retrieving an old release, verify its digest, run a smoke test, and check its SBOM/provenance.

Store cleanup and restore test reports to prove the retention policy is enforced. If the policy changes, record the version, approver, and effective date.

## 29. Checklist before enabling production cleanup

- [ ] Artifacts are classified into CI, snapshot, release, cache, and evidence.
- [ ] Each class has an owner and retention period.
- [ ] Age calculation timestamps are defined.
- [ ] Release repository rejects redeploying already published versions.
- [ ] Snapshot cleanup retains enough builds for rollback/debugging.
- [ ] Currently supported stable releases are protected.
- [ ] SBOM, checksums, signatures, and provenance follow the artifact.
- [ ] Build logs and test reports have separate retention.
- [ ] Deployment inventory is cross-checked before deleting releases.
- [ ] Legal holds and audit holds are checked.
- [ ] Backups include database, metadata, and blob storage.
- [ ] Restore tests have run successfully.
- [ ] Cleanup dry run has been reviewed.
- [ ] Publish, delete, and retention-bypass permissions are separated.
- [ ] Cleanup reports and audit trails are stored.
- [ ] Storage compaction/garbage collection is scheduled if needed.
- [ ] Catalog/archive manifest allows locating old artifacts.

## 30. References

- Apache Maven — Repository Layout: https://maven.apache.org/repositories/layout.html
- Apache Maven — Repository Metadata: https://maven.apache.org/repositories/metadata.html
- Sonatype Nexus — Maven Repositories: https://help.sonatype.com/en/maven-repositories.html
- Sonatype Nexus — Cleanup Policies: https://help.sonatype.com/en/cleanup-policies.html
- Sonatype Nexus — Maven SNAPSHOT Tasks: https://help.sonatype.com/en/maven-snapshot-tasks.html
- JFrog Artifactory — Retention Policies: https://docs.jfrog.com/administration/docs/retention-policies
- JFrog Artifactory — Cleanup Policies: https://docs.jfrog.com/administration/docs/cleanup-policies
- GitHub Actions — Store and share workflow artifacts: https://docs.github.com/en/actions/tutorials/store-and-share-data
- GitHub — Manage Actions artifact and log retention: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
- Amazon S3 — Locking objects with Object Lock: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html

Artifact retention must be tied to the actual lifecycle of each type of Java build data. Keep releases immutable during their support period, clean up snapshots and CI outputs by age/count, store SBOMs and provenance alongside digests, protect legal holds, and test restores before deleting authoritative copies.