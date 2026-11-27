# Storing Commit, Build Run, and Related Dependency Information

When a JAR file is deployed to production, looking only at the filename and version number is rarely enough to answer critical questions: Which commit produced this artifact? Which pipeline built it? Which JDK and build tool ran the build? Which dependencies were included? Is the exact artifact tested in staging the one running in production?

The information that answers those questions establishes **artifact traceability**. Every artifact must be linked to the source code, build run, tooling, and dependencies that produced it. When a security incident or post-release bug occurs, the team can trace back from the running artifact to the corresponding commit and build run, and then identify which components require investigation.

A filename like **service-2.4.0.jar** is merely a label. It does not prove its contents were built from tag **v2.4.0**, does not confirm the build succeeded, and does not reveal the actual dependencies inside. To establish trustworthy evidence, you must store structured metadata, the artifact checksum, the dependency list, and provenance bound to the exact output.

## 1. Distinguishing Version, Commit, Build Run, and Artifact

These identifiers are related, yet none can substitute for another:

| Identifier | Description | Example |
|---|---|---|
| Product version | The product version published by the team | 2.4.0 |
| Git commit | The checked-out source code state | a1b2c3d4... |
| Git ref | The branch or tag triggering the build | refs/tags/v2.4.0 |
| Build run ID | A specific pipeline execution | run-18452 |
| Build attempt | The attempt number within a run upon retry | attempt-2 |
| Artifact name | Name of the stored output | service-2.4.0.jar |
| Artifact digest | Content fingerprint of the file | sha256:... |
| SBOM | List of software components inside the artifact | service-2.4.0.cdx.json |

A single commit can be built multiple times. For instance, the first build fails due to a runner disconnect; the second attempt succeeds. Both runs share the same commit, yet differ in build ID, timestamp, environment, and potentially artifact digest if the build is not reproducible.

Conversely, a single build run can produce multiple artifacts: JARs, test files, container images, SBOMs, reports, and deployment bundles. Each artifact needs its own identifier and digest. Never assume a single build ID serves as the checksum for every output.

### A Complete Traceability Chain

~~~text
Git repository
    |
    v
Commit SHA + Git ref
    |
    v
CI workflow + build run ID
    |
    +---- Build tool / JDK / runner image
    |
    +---- Lockfiles / resolved dependencies
    |
    v
Artifact + SHA-256 digest
    |
    +---- SBOM
    |
    +---- Build provenance / attestation
    |
    v
Artifact repository
    |
    v
Staging ---- verify digest ----> Production
~~~

When a release experiences an incident, the team can trace backward from the deployed artifact digest to its provenance, build run, commit, and resolved dependency graph.

## 2. Source Code Information to Record

Every build should record enough information to pinpoint the exact state of the source code:

- Unique repository or project identifier.
- Full commit SHA, not merely the first few characters.
- Git ref: branch, tag, or pull request ref.
- Target branch commit or merge result commit when building a pull request.
- Working tree status at build time.
- Submodule revisions if the repository uses Git submodules.
- Revision of the pipeline file or build configuration whenever determinable.

The commit SHA is the core identifier, yet it is insufficient if the build fetches additional content outside the repository. For example, the pipeline might download scripts from an unpinned URL, read configuration files on the runner, or use source code generated from an external service. Those inputs must also be recorded or controlled.

### Building from a Clean State

Release pipelines should check out the exact commit and verify the working tree has no unexpected changes. If building from an existing workspace, stale files or uncleaned generated sources can affect the artifact in ways the commit SHA does not reflect.

With Git, you can record the commit and working tree status:

~~~bash
git rev-parse HEAD
git status --porcelain
git submodule status --recursive
~~~

If `git status --porcelain` produces output during a build expected to be clean, investigate the modified files. Some pipelines intentionally generate version files or generated sources prior to packaging; in that case, clearly distinguish build-generated inputs and record how they were produced.

### Distinguishing Head Commit and Merge Result

For pull requests, CI may test the source branch's head commit or a temporary merge commit combining source and target branches. These two states are not necessarily identical. If the artifact is built from the merge result, metadata must store that exact SHA along with related head/base information. Recording only the head SHA when the build actually used the merge result causes traceability to misrepresent the inputs.

### Do Not Confuse Commit Time with Build Time

Git records the commit timestamp when the commit was created. The build timestamp is when the pipeline executed the build. These two moments can be hours or days apart. Store build start and completion times separately in UTC, using a format with an explicit timezone.

## 3. Build Run Information to Record

The build run bridges source code and artifact. A build record should capture:

| Group | Suggested Data Fields | Purpose |
|---|---|---|
| Identification | Build ID, run attempt, workflow name | Distinguish executions |
| Source | Repository, commit SHA, ref, merge SHA | Identify source inputs |
| Timing | Started at, completed at, timezone | Investigate ordering and duration |
| CI | Provider, workflow URL, job IDs | Open exact logs and evidence |
| Toolchain | JDK, Gradle/Maven, compiler, and plugins | Reproduce the build environment |
| Runner | OS, architecture, container image digest | Identify the execution environment |
| Configuration | Build parameters, profile, feature options | Understand how the artifact was built |
| Outputs | Status, artifact names, and digests | Link outputs to the build run |
| Security | Builder identity, provenance signature | Verify build origin |

Not every field needs to be embedded inside the JAR manifest. Some metadata can live inside the artifact, detailed fields in a separate build-info or provenance file, and logs inside the CI system. What matters is that records share linkable identifiers and are retained long enough to support the release lifecycle.

### Build ID Differs from Product Version

A product version typically carries meaning for users or release management, such as `2.4.0`. A build ID identifies a single execution, such as `18452`. If the same version is rebuilt after fixing a pipeline issue, the two runs still require two distinct build IDs.

Never overwrite an already published version's artifact with different content while keeping the same identifier and path. If a rebuild is necessary, create a new build record, store the new digest, and handle it according to release policy. This prevents a tag or filename from pointing to different contents over time.

## 4. Embedding Basic Metadata in Java Artifacts

For JAR files, certain details can be placed into `META-INF/MANIFEST.MF`, such as version, commit revision, and build ID. This helps when an engineer holds only the JAR file and needs to identify its origin.

### Gradle Kotlin DSL Example

In `build.gradle.kts`:

~~~kotlin
tasks.jar {
    manifest {
        attributes(
            mapOf(
                "Implementation-Title" to project.name,
                "Implementation-Version" to project.version.toString(),
                "SCM-Revision" to providers.environmentVariable("GITHUB_SHA")
                    .orElse("unknown").get(),
                "Build-Run-Id" to providers.environmentVariable("GITHUB_RUN_ID")
                    .orElse("local").get()
            )
        )
    }
}
~~~

This example uses GitHub Actions environment variables. On other CI platforms, map the corresponding system variables. Local builds lacking CI variables receive fallback values; never allow `unknown` for release artifacts if policy requires full traceability.

### Maven Example

The Maven JAR Plugin can be configured to add manifest entries in `pom.xml`:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-jar-plugin</artifactId>
      <version>3.4.2</version>
      <configuration>
        <archive>
          <manifestEntries>
            <Implementation-Title>order-service</Implementation-Title>
            <Implementation-Version>2.4.0</Implementation-Version>
            <SCM-Revision>a1b2c3d4e5f6789012345678901234567890abcd</SCM-Revision>
            <Build-Run-Id>18452</Build-Run-Id>
          </manifestEntries>
        </archive>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

The values shown are illustrative. In CI, pass the commit and build ID via environment variables or controlled build parameters. Avoid editing `pom.xml` on every build just to write a new value.

### Limitations of Manifest Metadata

A manifest is a suitable place for brief, readable details. It is not a complete provenance store and does not prove the metadata was not altered. To verify integrity, compute the artifact's digest and store signed metadata/provenance or use a separate verification mechanism.

Embedding a build timestamp or build ID inside a JAR can cause two builds from the same commit to produce different bytes. If reproducible builds are a goal, consider moving per-run fields to an external metadata file outside the artifact, or normalizing timestamps and inputs according to policy.

## 5. Storing Structured External Build-Info

A JSON or properties file accompanying the artifact can record far richer fields than a manifest. Example `build-info.json`:

~~~json
{
  "schemaVersion": 1,
  "artifact": {
    "name": "order-service-2.4.0.jar",
    "version": "2.4.0",
    "sha256": "REPLACE_WITH_COMPUTED_DIGEST"
  },
  "source": {
    "repository": "https://example.org/platform/order-service",
    "commit": "a1b2c3d4e5f6789012345678901234567890abcd",
    "ref": "refs/tags/v2.4.0",
    "dirty": false
  },
  "build": {
    "id": "18452",
    "attempt": 1,
    "provider": "github-actions",
    "startedAt": "2026-11-18T08:00:00Z",
    "completedAt": "2026-11-18T08:04:32Z",
    "jdk": "17",
    "buildTool": "Gradle 8.10.2",
    "runner": "linux-x64"
  },
  "dependencies": {
    "lockfile": "gradle.lockfile",
    "lockfileSha256": "REPLACE_WITH_LOCKFILE_DIGEST",
    "sbom": "order-service-2.4.0.cdx.json"
  }
}
~~~

This illustrates the data structure. Digest values must be computed from actual files; never leave placeholders in release metadata. Repository URLs, build URLs, and other fields must reflect the project's real sources.

If `build-info.json` were placed inside the JAR, the `artifact.sha256` field could not contain the final digest of that same JAR without creating a circular dependency: modifying a file inside the JAR changes the JAR's digest. Common practice is:

- Embed source/build metadata inside the JAR if needed.
- Compute the digest after the JAR is finalized.
- Store the digest in an external release manifest, registry metadata, or attestation.
- Link external records to the exact artifact by name and digest.

### Using a Versioned Schema Format

When metadata is read by multiple systems, define a schema and schema version. This helps release tools, dashboards, and inventory systems understand which fields are required, which are optional, and how to evolve the structure without breaking older consumers.

Key fields should have explicit data types. Timestamps should use ISO 8601/RFC 3339 with UTC or an explicit offset. Digests should specify the algorithm, such as `sha256:<hex>`. Dependency lists should contain package identifiers and versions, not just display names.

## 6. Recording Actual Dependencies

Keeping only `pom.xml` or `build.gradle` is not enough to know exactly which dependencies went into an artifact. Build files declare rules; actual dependency resolution also depends on version constraints, BOMs, lockfiles, repository metadata, profiles, and transitive dependencies.

A useful dependency record should capture:

- Resolved package name and version.
- Package ecosystem, such as Maven or npm.
- Group ID and artifact ID for Maven.
- Scope or configuration, such as compile, runtime, or test.
- Direct vs. transitive dependency.
- Repository or distribution source.
- Package checksum or digest where available.
- License and security reference data if collected.

### Lockfiles and Dependency Graphs

A lockfile captures versions resolved under the tool's rules. With Gradle, you can enable dependency locking for controlled configurations and commit the lock state. With Maven, versions can be managed via dependency management/BOMs and internal repositories; projects requiring locked resolution graphs can add appropriate verification mechanisms.

Lockfiles help builds reuse identical dependency versions, yet you still must verify downloaded artifact contents. If a repository swaps the content behind existing coordinates, checksum verification or repository immutability catches the issue.

### Capturing Transitive Dependencies

A single direct library can pull in many other libraries. When a CVE is disclosed, the team must know which artifacts contain the affected package, even if that package was never declared directly in the build file.

Therefore, store the resolved dependency graph or an SBOM generated from the exact artifact/build. A list of direct dependencies alone cannot fully answer which components exist in the product.

## 7. SBOMs Add a Software Component View

A **Software Bill of Materials (SBOM)** is an inventory of software components inside a product or artifact. An SBOM typically describes packages, versions, identifiers, dependency relationships, and license or origin details.

Two common formats:

- **CycloneDX:** a BOM-focused format with fields tailored for component analysis, security, and supply chain use cases.
- **SPDX:** a standard format for describing packages, files, licenses, and software component metadata.

An SBOM should be generated from the exact dependency graph or artifact being released. If a build produces multiple modules or images, clarify whether the SBOM describes the entire product or a single component. Bind the SBOM to the artifact via digest or an unambiguous identifier.

### Example SBOM Workflow

~~~text
Resolve dependencies
        |
        v
Build application artifact
        |
        v
Collect resolved components
        |
        v
Generate CycloneDX or SPDX SBOM
        |
        v
Store SBOM + artifact digest
        |
        v
Scan dependencies and retain report
~~~

Do not generate an SBOM from a separate resolution run after the build if the dependency graph could change between runs. Use resolution data from the actual build run or verify the SBOM directly against the released artifact.

An SBOM is not a certification that a product is secure. It reports components declared within the SBOM's scope; teams still need to scan, assess exploitability, check licenses, and monitor vulnerabilities.

## 8. Generating Digests and Linking to Artifacts

Once a build finishes, compute a checksum to identify the artifact's exact contents. SHA-256 is a common choice:

~~~bash
# Linux
sha256sum build/libs/order-service-2.4.0.jar

# PowerShell
Get-FileHash .\build\libs\order-service-2.4.0.jar -Algorithm SHA256
~~~

The digest should be stored alongside:

- Artifact name and version.
- Build run ID.
- Commit SHA.
- Repository or registry location.
- Creation timestamp and creating user/identity.
- Corresponding SBOM and provenance.

Filenames can stay stable for users, but the digest is the true content identifier. Two files with the same name can differ byte-for-byte. Two copies with matching SHA-256 digests have very high confidence of identical contents; when verification is needed, recompute the digest from the downloaded file.

### Storing Checksums Alongside Artifacts

A checksum file can be published alongside the artifact:

~~~text
order-service-2.4.0.jar
order-service-2.4.0.jar.sha256
order-service-2.4.0.cdx.json
order-service-2.4.0.build-info.json
~~~

A sidecar checksum file detects download or storage corruption. However, if an attacker can replace both the artifact and the checksum file, a checksum alone does not prove trustworthy origin. Critical release pipelines require digital signatures or attestations verified by a trusted identity.

## 9. Provenance: Evidence of How the Artifact Was Built

**Build provenance** describes the origin and process that produced an artifact. It typically links:

- Subject: the artifact and its digest.
- Source: repository and commit.
- Builder: system or identity executing the build.
- Build definition: workflow, script, or configuration used.
- Invocation: parameters and trigger context.
- Materials: dependencies and relevant inputs.
- Metadata: timestamps, run details, and required attributes.

Models such as SLSA provenance and in-toto attestations provide structured formats for expressing this evidence. Attestations can be stored beside the artifact or in a system searchable by digest.

Provenance differs from self-reported build-info. A JSON file written by the build script itself helps traceability, but if unprotected, anyone able to alter the artifact could also alter the metadata. Signed attestations with verified builder identities strengthen confidence in the information source.

### Signing and Verifying Attestations

In a release system, the builder can sign provenance using managed keys or short-lived CI identities via an appropriate authentication mechanism. The deployment side verifies the signature, identity, repository, workflow, and subject digest before permitting use of the artifact.

Never check solely for the presence of a signature. Policies must specify:

- Which identities are authorized to sign.
- Which repositories and workflows are allowed to produce artifacts.
- Which branches or tags are eligible for release.
- Whether the artifact digest matches the subject in the attestation.
- Whether provenance satisfies builder and build definition requirements.

Never place private signing keys, tokens, or secrets into build-info or SBOMs. Use a secret manager or appropriate identity/OIDC mechanisms to grant signing rights, scoped by repository, workflow, and environment.

## 10. Example: Collecting Metadata in GitHub Actions

GitHub Actions provides environment variables for recording run and source details:

- `GITHUB_REPOSITORY`: repository executing the workflow.
- `GITHUB_SHA`: commit associated with the event.
- `GITHUB_REF`: branch or tag ref.
- `GITHUB_RUN_ID`: workflow run identifier.
- `GITHUB_RUN_ATTEMPT`: attempt number of the run.
- `GITHUB_WORKFLOW`: workflow name.

Example writing a simple build-info file after building:

~~~yaml
name: Build and describe artifact

on:
  push:
    tags:
      - "v*"

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - name: Build
        run: ./gradlew --no-daemon clean build

      - name: Create build metadata
        shell: bash
        run: |
          mkdir -p build/release-metadata
          cat > build/release-metadata/build-info.txt <<EOF
          repository=$GITHUB_REPOSITORY
          commit=$GITHUB_SHA
          ref=$GITHUB_REF
          workflow=$GITHUB_WORKFLOW
          run_id=$GITHUB_RUN_ID
          run_attempt=$GITHUB_RUN_ATTEMPT
          java_version=$(java -version 2>&1 | head -n 1)
          gradle_version=$(./gradlew --version | grep '^Gradle ' | head -n 1)
          EOF

      - name: Calculate artifact digest
        shell: bash
        run: |
          sha256sum build/libs/*.jar > build/release-metadata/SHA256SUMS

      - name: Upload release evidence
        uses: actions/upload-artifact@v4
        with:
          name: release-evidence
          path: |
            build/libs/*.jar
            build/release-metadata/
~~~

This example illustrates collecting a subset of fields. Adapt artifact paths, filenames, workflows, and action versions to your project. `GITHUB_SHA` depends on the event type; for pull requests it may represent a platform-created merge commit. If both head SHA and base SHA are needed, extract them from the event payload and document each field's meaning clearly.

The example above only generates build-info and checksums; it does not yet generate an SBOM, sign provenance, or prove independent/reproducible builds. Workflow artifact uploads serve as run-scoped evidence; official release artifacts should still be pushed to a registry or artifact repository with appropriate retention and access controls.

### Avoid Putting Untrusted Data into Metadata

Branch names, tag names, commit messages, and pull request data can contain special characters or user-controlled content. When writing to JSON, properties, or shell scripts, escape values properly per format and avoid interpolating untrusted data directly into shell commands. Never put secrets, tokens, sensitive configuration contents, or credential-bearing URLs into metadata.

## 11. Storing Artifacts and Promoting the Same Artifact Across Environments

Once an artifact is built and verified, store it in an artifact repository or container registry with:

- Stable path or coordinates.
- Version and build ID.
- Digest.
- Build metadata and provenance.
- SBOM and verification reports.
- Retention policies and access controls.
- Upload, download, and deployment audit trails.

A sound workflow builds an artifact once, then promotes the same digest across dev, staging, and production. Do not rebuild from source in each environment assuming identical results. Rebuilding can pull in different dependencies, plugins, base images, or environment state.

Example:

~~~text
Build commit a1b2c3
       |
       v
order-service.jar
sha256:abc123...
       |
       v
Artifact repository
       |
       +---- Deploy staging (digest abc123...)
       |
       +---- Verify smoke test / quality gate
       |
       v
Promote same digest
       |
       v
Deploy production (digest abc123...)
~~~

For container images, prefer deploying by digest rather than relying solely on mutable tags. For example, `registry.example.com/order-service@sha256:...` identifies specific image contents; tag `2.4.0` can be moved if the registry allows overwrites.

### Separating Environment Configuration from Artifacts

Artifacts should contain the application and components required to run. Environment configuration such as endpoints, feature flags, secrets, and connection details should be supplied at deploy time via configuration/secret management mechanisms. Building a separate artifact per environment undermines the ability to prove staging tested the exact binary deployed to production.

If an artifact genuinely needs to differ per environment, determine whether that difference is truly runtime configuration or a build input. Record every build input that alters artifact contents.

## 12. Tracing Backward from Artifacts to Commits and Dependencies

When a vulnerability is discovered in a library, the team must answer: which artifacts contain that library, which commit built them, and which environments are running them?

Traceability can work in reverse:

1. Retrieve the artifact digest from the registry or running environment.
2. Look up the build record or attestation by digest.
3. Verify the signature and builder identity.
4. Read the commit SHA, Git ref, build run ID, and build definition.
5. Retrieve the SBOM or dependency graph for that exact artifact.
6. Find affected packages, versions, and dependency paths.
7. Identify releases and environments using that digest.
8. Plan dependency updates, build a new artifact, and deploy per policy.

Forward traceability from commit to artifact must also be supported. When a commit is merged, the team should be able to find all build runs that created artifacts from that commit, check their digests, and see which artifacts were promoted.

### Recording Deployment History

A deployment record should link:

- Artifact digest.
- Target environment.
- Start and completion timestamps.
- Configuration version or config revision.
- Deployment run ID.
- Health check and smoke test results.
- Initiating user or identity.
- Rollback outcome if applicable.

This allows the team, during a production incident, to pinpoint the actual binary, the build that produced it, and related dependencies instead of guessing from release labels or image names.

## 13. Retaining Metadata and Evidence

Artifacts may be retained longer than routine CI logs. If logs are deleted after a short window while the artifact remains deployed, traceability breaks. Define retention for each data category:

| Data | Retention Policy Considerations |
|---|---|
| Release artifacts | Retain per product support lifecycle and rollback requirements |
| Digests/checksums | Retain for the same duration as the artifact |
| Build-info | Retain for the same duration as the artifact or longer |
| Provenance/attestations | Retain long enough to verify all artifacts in use |
| SBOMs | Retain per artifact version and vulnerability management requirements |
| Build logs | Retain per investigation needs and organizational policy |
| Deployment records | Retain per environment lifecycle and audit requirements |
| Test/security reports | Retain per quality, security, and compliance requirements |

You do not need to keep every verbose log indefinitely. However, the minimal records identifying an artifact's origin, content, and deployment history must persist for as long as the artifact remains supported or in use.

## 14. Common Mistakes

### Storing Only Version and Filename

A version does not reveal the commit or build run. Two artifacts with the same filename can differ in contents. Record commit SHA, build ID, and digest to distinguish them.

### Storing Only Commit SHA

A commit does not describe the JDK, build tool, resolved dependencies, runner, or build parameters. Record the corresponding toolchain, lockfile, SBOM, and provenance.

### Relying Only on Build Logs

Logs can expire, are hard to query, and are not guaranteed to bind cleanly to the deployed artifact. Generate structured metadata and link it by digest.

### Rebuilding Artifacts in Each Environment

Rebuilding can produce different binaries. Build the artifact once, verify it, and promote the exact same digest across environments.

### Using Checksums as Proof of Origin

Checksums detect content changes when the reference value is trusted. If both file and checksum are replaced, checksums cannot prove who created the artifact. Use signatures and provenance to verify origin.

### Generating SBOMs from Declared Dependencies Instead of Actual Dependencies

A dependency graph can include many transitive packages or depend on resolution rules. SBOMs must reflect the actual components packaged into the released artifact.

### Embedding Build IDs and Timestamps Without Considering Reproducibility

Metadata that changes on every run causes artifacts to differ byte-for-byte even from identical source. Decide which fields live inside the artifact and which live in external provenance based on reproducibility goals.

### Putting Secrets into Build Metadata

Build-info and SBOMs are often distributed more broadly than internal logs. Never write tokens, passwords, private keys, or credential-bearing URLs into these files.

## 15. Pre-Release Artifact Checklist

- [ ] Artifact was built from a specific commit SHA and Git ref.
- [ ] Build run ID and attempt are recorded.
- [ ] Working tree was clean or any generated changes are documented.
- [ ] JDK, build tool, plugins, and runner environment are recorded.
- [ ] Dependency lockfile and lockfile digest are saved.
- [ ] SBOM reflects the artifact's actual dependencies.
- [ ] Artifact has a SHA-256 digest computed after build completion.
- [ ] Build-info and provenance bind to the exact artifact digest.
- [ ] Signatures/attestations are verified against identity and trust policy.
- [ ] Artifact is stored in a repository with appropriate retention and access controls.
- [ ] Staging and production use the exact same verified artifact digest.
- [ ] Deployment records link the artifact to environments and verification results.
- [ ] Metadata contains no secrets or sensitive data.

Artifact traceability lets teams know precisely where a running binary came from, which tools built it, and which components it contains. When commits, build runs, dependencies, SBOMs, digests, and provenance are linked together, incident investigation, vulnerability assessment, auditing, and redeployment rest on solid evidence. More importantly, teams can promote the exact tested artifact across environments and verify content by digest instead of relying on filenames or version labels.
