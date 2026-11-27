# Identifying Artifacts by Source, Toolchain, Build Configuration, and Checksum

A native executable or container image with only a name and version is not enough for traceability. When a production bug or dependency vulnerability is discovered, operations teams must be able to answer: which commit built this binary, which GraalVM/JDK and compiler built it, which dependencies and reachability metadata were used, with which build options, for which architecture, and whether the running bytes are the exact artifact that was tested.

For a Spring Boot application compiled with **Spring AOT and GraalVM Native Image**, artifact identity requires four groups of data: **source revision**, **toolchain**, **build configuration/dependencies**, and **artifact digest**. CI/CD should record these in a build manifest, generate SBOM/provenance attestations, verify signatures and checksums, and publish/deploy the exact artifact by digest.

This lesson belongs to the **CI/CD** chapter of the **`SPRING_BOOT_NATIVE_IMAGE`** module. The module teaches compiling Spring Boot into GraalVM Native Image to evaluate startup/memory, practicing Maven/Gradle, reflection/resource hints, compatibility testing, container packaging, and operating native builds. This lesson focuses on attaching verifiable identity to binaries and images across the entire pipeline.

## 1. Artifact Identity, Checksum, and Provenance Are Three Distinct Concepts

A trustworthy release process must distinguish:

| Concept | Question it answers | Example |
|---|---|---|
| Artifact identity | Which exact product are we referring to? | `orders-service:1.4.0`, target `linux/amd64` |
| Checksum/digest | Do the bytes match a known fingerprint? | SHA-256 of the executable or OCI manifest |
| Build provenance | Where, with what, and by which process was the artifact built? | Commit, builder identity, toolchain, dependencies, build parameters |
| Signature/attestation | Who or which platform vouches for the metadata tied to this digest? | Signed in-toto/SLSA provenance |
| SBOM | Which software components are inside the artifact or participated in the build? | SPDX/CycloneDX dependency inventory |

A checksum detects altered bytes when compared against a trusted value. However, an `artifact.sha256` file stored alongside the binary does not by itself prove who built the binary: anyone who swaps the binary can swap the checksum file too. Provenance records the relationship between source, builder, inputs, and output; a signature from a trusted builder authenticates that attestation.

SBOMs and provenance do not replace each other either. An SBOM describes software components; provenance describes how the artifact was produced. Both should be bound to the digest of the exact released artifact.

## 2. Native Image Product Identity Model

A release build can be represented by the tuple:

\[
\text{Product Identity} =
(\text{name},\text{version},\text{source},\text{toolchain},
\text{dependencies},\text{configuration},\text{platform},\text{digest})
\]

For Spring Boot Native Image, each field has a specific meaning:

| Group | Data to record |
|---|---|
| Product | Service name, release version, build ID, artifact type |
| Source | Repository URI, Git commit SHA, tree SHA, tag, working tree state, submodule revisions |
| Toolchain | Builder image digest, OS baseline, CPU architecture, JDK/GraalVM version, `native-image` version, C/C++ compiler/linker, Maven/Gradle and plugin versions |
| Dependencies | Dependency tree, lockfiles, checksum/signature verification metadata, SBOM |
| Build configuration | Spring profiles used during AOT, Maven/Gradle tasks/profiles, Native Image arguments, build properties, `RuntimeHints`/reachability metadata |
| Target | `linux/amd64`, `linux/arm64`, libc baseline, dynamic/static linking |
| Output | Native executable SHA-256, container OCI digest, SBOM digest, provenance reference |

An amd64 release and an arm64 release are two different binaries with different digests, even when built from the same source commit and version. When publishing a multi-architecture image, the OCI manifest list has its own digest pointing to the individual platform manifests.

Never use a tag like `latest` or a version string as the sole identity. Tags can be moved to another image; a digest identifies exact manifest contents.

## 3. Recording the Source Revision

Release builds should start from an immutable commit. CI must record:

- Repository URI.
- Full commit SHA, not just a short SHA.
- Git tree SHA or source archive checksum.
- Release tag and version.
- Whether the working tree is clean.
- Commit SHAs of submodules and revisions of Git LFS objects if used by the project.

Example source check in Linux CI:

~~~bash
git rev-parse HEAD
git rev-parse HEAD^{tree}
git status --porcelain
git submodule status --recursive
~~~

Release pipelines should fail if `git status --porcelain` reports uncommitted changes. A build from a working tree containing local edits or uncommitted generated files is hard to reproduce from a commit SHA.

If a source archive checksum is needed:

~~~bash
git archive --format=tar HEAD | sha256sum
~~~

Note that `git archive` does not automatically include submodule contents like regular files; record submodule revisions separately or construct a source bundle via a defined procedure. For Git LFS, record object IDs and ensure CI checked out the actual object bytes.

### Build ID

The build ID should distinguish each pipeline execution, even when the same commit is rebuilt. For example:

~~~text
orders-service-1.4.0+git.7f2a9c1-build.1842
~~~

Build IDs are for looking up CI logs, not as replacements for commit SHAs or artifact digests. Two builds from the same commit can yield different outputs if toolchains, dependencies, environments, or build parameters differ.

## 4. Identifying the Toolchain and Builder Image

Native Image depends on more than the JDK version. Outputs can change when upgrading GraalVM, Native Build Tools, the Spring Boot plugin, compiler, linker, operating system, or CPU architecture.

CI should record at least:

~~~bash
java -version
native-image --version
mvn -version
cc --version
ld --version
uname -a
~~~

If using Gradle, record `./gradlew --version` and the Native Build Tools plugin version. With Maven, record the Maven Wrapper version, Spring Boot Maven plugin, and `native-maven-plugin` version.

### Pin the Builder Image by Digest

A tag such as `ghcr.io/graalvm/native-image-community:21-ol9` is convenient to read but can be overwritten. For release pipelines, pin the image digest:

~~~dockerfile
FROM ghcr.io/graalvm/native-image-community:21-ol9@sha256:<BUILDER_IMAGE_DIGEST> AS builder
~~~

Replace `<BUILDER_IMAGE_DIGEST>` with a CI/registry-verified digest. Record both the image reference and digest in the build manifest. The runtime base image must also be pinned and recorded.

For the native compiler, record explicitly:

- GraalVM distribution and version.
- `native-image --version`.
- JDK feature version.
- Compiler/linker versions.
- Builder OS, glibc/musl baseline, and architecture.
- Native Build Tools plugin version.

Two builds from the same source using different toolchains must not be treated as the same build recipe.

## 5. Identifying Dependencies and Verifying Integrity

A version string tells you which dependency was requested, which is not enough to verify the downloaded bytes. CI must lock the dependency graph and verify input artifacts.

### 5.1. Maven

With Maven:

- Pin versions for dependencies, Maven plugins, and build extensions.
- Avoid version ranges and `SNAPSHOT`s in release builds.
- Use the Maven Wrapper and pin the Maven distribution.
- Use an internal repository manager or vetted repositories.
- Configure checksum policy as `fail` on repositories when required by policy.
- Save the dependency tree/effective POM as evidence of the dependency graph.

Example repository checksum policy configuration:

~~~xml
<repositories>
    <repository>
        <id>central</id>
        <url>https://repo.maven.apache.org/maven2</url>
        <releases>
            <enabled>true</enabled>
            <checksumPolicy>fail</checksumPolicy>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
~~~

`checksumPolicy=fail` causes Maven to abort if repository-supplied checksums are missing or fail to match under that policy. It does not replace publisher signature verification or validating repository origin; checksums fetched from the same repository still need to be evaluated within the organization's trust model.

Record the dependency graph:

~~~bash
./mvnw -B -ntp dependency:tree \
  -DoutputFile=target/dependency-tree.txt
~~~

Pin the Maven Wrapper distribution with a checksum in `.mvn/wrapper/maven-wrapper.properties` if your project's wrapper setup supports `distributionSha256Sum`. Verify plugin versions and build configuration alongside source; do not pin only application dependencies while overlooking the plugins that produce the native binary.

### 5.2. Gradle Dependency Locking and Verification

Gradle provides two complementary mechanisms:

- **Dependency locking:** pins resolved dependency versions.
- **Dependency verification:** verifies checksums and/or signatures of downloaded artifacts.

Enable dependency locking:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Generate or update lock state after reviewing dependencies:

~~~bash
./gradlew dependencies --write-locks
~~~

Generate SHA-256 verification metadata:

~~~bash
./gradlew --write-verification-metadata sha256 build
~~~

Gradle writes metadata to:

~~~text
gradle/verification-metadata.xml
~~~

Commit lockfiles and verification metadata to source control. When dependencies or plugins change, review new checksums before accepting them. Bootstrapping verification metadata from a repository does not by itself prove the repository is trustworthy; verify artifact origins, especially for critical dependencies.

If publishers provide signatures and the organization maintains trusted keys, enable signature verification alongside checksum verification. Checksums verify content; signatures verify the publisher against a configured trust store.

## 6. Identifying the Build Configuration

A single source commit can yield multiple distinct native executables if build properties differ. Record:

- Maven profile or Gradle task invoked.
- Spring profiles and properties used during Spring AOT processing.
- Native Image arguments, GC, optimization level, PGO profile, and target architecture.
- Runtime hints, reachability metadata, and resource configuration.
- Environment variables affecting the build.
- Build scripts, wrapper configuration, and plugin versions.
- Dockerfile, `.dockerignore`, and builder/runtime image references.

Example build configuration for production:

~~~text
Build command: ./mvnw -Pnative -DskipTests native:compile
Spring AOT profile: production
Target: linux/amd64
GraalVM: Java 21, pinned GraalVM release
Native Image flags: --gc=<approved-gc>, <approved-options>
Builder image: ghcr.io/graalvm/native-image-community@sha256:...
~~~

This is an illustrative example; commands and profiles must reflect the actual project. If AOT runs with the `production` profile but runtime needs the `staging` profile's bean set, build a separate variant or confirm both profiles preserve the exact same bean topology.

### Never Write Secrets into Provenance

Build parameters and environment metadata should suffice to reproduce a build, but never write passwords, tokens, private keys, signing credentials, or secret contents into manifests/attestations. Use secret mounts or CI secret stores. Record secret reference names/versions if policy allows, never secret values.

When Docker BuildKit produces provenance with `mode=max`, more build arguments and build details are recorded. Therefore, never pass secrets via Docker `ARG` or `ENV`; use BuildKit secret mounts instead.

## 7. Creating a Build Manifest for the Native Executable

A `build-info.json` file provides a human- and release-system-readable summary. It does not replace signed SLSA provenance, but enables quick lookups by operations teams.

Example:

~~~json
{
  "schemaVersion": 1,
  "product": {
    "name": "orders-service",
    "version": "1.4.0",
    "buildId": "orders-service-1.4.0-build-1842",
    "artifactType": "graalvm-native-executable"
  },
  "source": {
    "repository": "https://github.com/acme/orders-service",
    "revision": "7f2a9c1d...full-commit-sha",
    "tree": "ab81e0...git-tree-sha",
    "dirty": false
  },
  "toolchain": {
    "builderImage": "ghcr.io/graalvm/native-image-community:21-ol9@sha256:...",
    "javaVersion": "21",
    "graalvmVersion": "recorded-version",
    "nativeImageVersion": "recorded-version",
    "nativeBuildToolsVersion": "recorded-version",
    "compiler": "recorded-compiler-version",
    "platform": "linux/amd64"
  },
  "build": {
    "command": "./mvnw -Pnative native:compile",
    "springAotProfile": "production",
    "nativeImageArguments": ["--gc=<approved-gc>"],
    "buildConfigurationSha256": "<sha256>",
    "dependencyManifestSha256": "<sha256>"
  },
  "artifact": {
    "file": "orders-service",
    "sha256": "<sha256-of-native-executable>"
  }
}
~~~

Values inside `<...>` are placeholders that the pipeline must populate with real data. Never commit a manifest with dummy versions or checksums into a release.

The manifest should be stored alongside the executable in the release bundle or in an artifact metadata store. If you want to bake `build-info.json` inside the container image, note that its contents become part of the image and alter the image digest. Alternatively, keep the manifest outside the image and attach an attestation to the final digest.

Never embed a binary's own digest inside the binary before computing that digest; doing so creates a self-referential cycle. Generate the sidecar manifest after the binary finishes building.

## 8. Hashing Build Inputs

In addition to the Git commit, you can generate a checksum file for the files describing the build:

~~~bash
sha256sum pom.xml \
  .mvn/wrapper/maven-wrapper.properties \
  Dockerfile \
  .dockerignore \
  > build-inputs.sha256
~~~

With Gradle:

~~~bash
sha256sum settings.gradle build.gradle gradle.properties \
  gradle.lockfile gradle/verification-metadata.xml \
  Dockerfile .dockerignore \
  > build-inputs.sha256
~~~

Adjust the list to match the files actually present in your project. For Kotlin DSL, include `settings.gradle.kts` and `build.gradle.kts`; for multi-project builds, include build files of subprojects and included builds. If custom reachability metadata, resource configs, or Native Image arguments live in separate files, include them in the input set.

The Git commit already identifies tracked files in the repository; the extra checksum file helps verify specific build inputs inside an artifact bundle. If the build generates sources or downloads toolchains from outside the repository, record them in the provenance/dependency manifest.

## 9. Generating SHA-256 for the Native Executable

Once native compilation completes, compute the checksum for the executable:

~~~bash
sha256sum target/orders-service > target/orders-service.sha256
~~~

With Gradle, replace the path with the actual output binary, for example:

~~~bash
sha256sum build/native/nativeCompile/orders-service \
  > build/native/nativeCompile/orders-service.sha256
~~~

Verify before publishing:

~~~bash
sha256sum --check target/orders-service.sha256
~~~

In PowerShell:

~~~powershell
Get-FileHash .\target\orders-service -Algorithm SHA256
~~~

SHA-256 is a fingerprint of the bytes at computation time. If even a single byte of the executable changes, the digest will almost certainly change. Do not use MD5 or SHA-1 for new security identification.

Store the checksum sidecar in the same release bundle, and protect the bundle with a signature/attestation or store the checksum in a trusted metadata system. If both the checksum and binary are downloaded from the same unauthenticated location, an attacker can alter both.

## 10. Identifying Container Images with OCI Digests

After packaging the executable into a container, the image has its own digest. This digest identifies the OCI image manifest/config/layers, not the checksum of the executable alone.

Build and push the image with Docker Buildx:

~~~bash
docker buildx build \
  --platform linux/amd64 \
  --provenance=mode=max \
  --sbom=true \
  --tag ghcr.io/acme/orders-service:1.4.0 \
  --push \
  --metadata-file buildx-metadata.json \
  .
~~~

Extract the digest from metadata output:

~~~bash
jq -r '."containerimage.digest"' buildx-metadata.json
~~~

Record the image reference as:

~~~text
ghcr.io/acme/orders-service@sha256:<OCI_IMAGE_DIGEST>
~~~

Deploy by digest rather than by tag alone. The `1.4.0` tag is helpful for humans, but can be moved by registry policy or anyone with write access. An immutable digest pinpoints the exact image contents that were tested.

### Multi-Architecture Images

For multi-arch images, the manifest list/index digest identifies the set of platform manifests. Each platform manifest has its own digest. Record all of:

- The deployed index/manifest-list digest.
- The platform (`linux/amd64` or `linux/arm64`).
- The corresponding platform manifest digest if the pipeline needs to audit individual binaries.

Never treat the checksum of an amd64 executable as the checksum for arm64. Each binary must have its own manifest and test evidence.

## 11. SBOMs for Both Build Inputs and Runtime Images

An SBOM lists software components such as libraries, versions, licenses, and package identifiers. For Native Image, two scopes matter:

1. **Build-time dependencies:** GraalVM, compiler/linker, Maven/Gradle, plugins, annotation processors, and libraries used during the build.
2. **Runtime/application dependencies:** Java libraries compiled into the executable and OS libraries required at container runtime.

Multi-stage Dockerfiles typically copy only the executable into the final stage. If an SBOM tool scans only the final stage, it may miss Maven/Gradle dependencies and the compiler used during the build. Docker BuildKit supports SBOM attestations; by default scanning focuses on the final stage, and contexts/stages can be configured to collect additional build-time materials.

Example enabling SBOM:

~~~bash
docker buildx build --sbom=true --push \
  --tag ghcr.io/acme/orders-service:1.4.0 .
~~~

The SBOM should be bound to the exact image digest and stored in the registry/attestation store. If generating a separate SBOM for the Maven/Gradle dependency graph, store that SBOM's digest in the build manifest or provenance.

An SBOM is an inventory, not proof that every package is safe. Pipelines still need vulnerability scanning, license policies, and CVE remediation workflows.

## 12. Build Provenance and in-toto/SLSA Attestations

**Provenance** is verifiable data about where, when, and how an artifact was created. SLSA Build Provenance defines several groups of fields:

- `builder`: the platform/build service that executed the build.
- `buildType`: the build process type or template.
- `externalParameters`: external inputs influencing the build.
- `resolvedDependencies`: resolved source/dependency inputs.
- `subject`: the output artifact identified by digest.

An in-toto Statement binds `subject` (artifact name and digest) to a `predicateType` and provenance payload. The attestation must be signed by the builder or a trusted identity so consumers can verify its origin.

Conceptual structure example:

~~~json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "orders-service",
      "digest": {
        "sha256": "<native-executable-digest>"
      }
    }
  ],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://example.com/buildtypes/spring-boot-native/v1",
      "externalParameters": {
        "sourceRevision": "<full-git-commit>",
        "target": "linux/amd64",
        "buildProfile": "production"
      },
      "resolvedDependencies": []
    },
    "runDetails": {
      "builder": {
        "id": "https://ci.example.com/builders/native-release"
      }
    }
  }
}
~~~

This is an example to illustrate the structure, not a self-trusted attestation. In production, use your CI platform or BuildKit to generate provenance, then sign the attestation with a trusted builder identity or CI signing service. Never hand-fill `builder.id` and treat self-authored JSON as trusted origin proof.

### BuildKit Provenance

Docker Buildx can attach a provenance attestation to the image:

~~~bash
docker buildx build \
  --provenance=mode=max \
  --sbom=true \
  --push \
  --tag ghcr.io/acme/orders-service:1.4.0 \
  .
~~~

`mode=max` records richer details about build parameters and materials than the minimal mode. Keep secrets out of build args/environment because detailed metadata can expose configuration details. The attestation is attached to the image; when pushing to a registry supporting OCI referrers/attestations, preserve the digest and associated metadata.

## 13. Signing Artifacts and Verifying Attestations

The pipeline should produce signatures or signed attestations once digests are established. You can use keyless signing via OIDC/Sigstore or keys managed by KMS/HSM per organizational policy.

With GitHub Actions, artifact attestations can bind provenance to binaries or container images. The workflow needs appropriate permissions—such as `id-token: write`, `contents: read`, and `attestations: write`—with attestation creation performed by the platform's supported action.

Verify a binary's attestation with the GitHub CLI:

~~~bash
gh attestation verify target/orders-service \
  -R acme/orders-service
~~~

Verify a container image's attestation:

~~~bash
gh attestation verify \
  oci://ghcr.io/acme/orders-service:1.4.0 \
  -R acme/orders-service
~~~

After verifying the signature, the consumer must still check policy:

- Does the repository/source revision match an allowed repository?
- Is the commit on an approved branch/tag?
- Is the builder identity on the allowlist?
- Is the workflow/build type a trusted release workflow?
- Do the toolchain, target platform, and build parameters comply with policy?
- Does the subject digest in the attestation match the digest of the artifact being deployed?
- Do dependencies/SBOMs violate any vulnerability or license policies?

An attestation does not guarantee an artifact has zero vulnerabilities. It verifies where and by which process the artifact was built; consumers must still evaluate source, dependencies, and test outcomes.

## 14. CI Pipeline for Spring Boot Native Image

A release pipeline can be divided into these gates:

~~~mermaid
flowchart TD
    A["Checkout immutable commit"] --> B["Verify clean tree + source identity"]
    B --> C["Pin builder/toolchain"]
    C --> D["Verify dependencies + lock/checksum"]
    D --> E["Run JVM tests + AOT/native tests"]
    E --> F["Build native executable"]
    F --> G["Create build manifest + SHA-256"]
    G --> H["Generate SBOM + provenance"]
    H --> I["Build OCI image + record digest"]
    I --> J["Sign/attest exact digest"]
    J --> K["Verify signature + release policy"]
    K --> L["Deploy by immutable digest"]
~~~

Example shell steps for a Linux runner:

~~~bash
set -euo pipefail

# 1. Source identity
GIT_COMMIT="$(git rev-parse HEAD)"
GIT_TREE="$(git rev-parse HEAD^{tree})"
test -z "$(git status --porcelain)"

# 2. Toolchain identity
java -version
native-image --version
./mvnw -version

# 3. Dependency graph
./mvnw -B -ntp dependency:tree \
  -DoutputFile=target/dependency-tree.txt

# 4. Build and test (use the project's approved native profile)
./mvnw -B -ntp verify
./mvnw -B -ntp -Pnative -DskipTests native:compile

# 5. Artifact checksum
sha256sum target/orders-service \
  > target/orders-service.sha256
sha256sum --check target/orders-service.sha256

# 6. Hash important build inputs
sha256sum pom.xml Dockerfile \
  .mvn/wrapper/maven-wrapper.properties \
  > target/build-inputs.sha256
~~~

Exact commands depend on how the project configures Maven Native Build Tools; some projects bind native compilation to `package`, while others invoke a dedicated goal/task. The pipeline must execute a single reviewed build definition and record the exact command run. Never run two consecutive native builds with different configurations and save only the checksum of the final output.

After creating the executable, the pipeline produces `build-info.json`, the SBOM, and provenance; then packages the image, records the OCI digest, signs/attests the digest, and runs policy verification before deploying.

### Recommended Release Gates

| Gate | Pass condition |
|---|---|
| Source | Full commit, clean working tree, submodules/LFS at verified revisions |
| Toolchain | Builder image digest and compiler/tool versions are on the allowlist |
| Dependencies | Locking/verification/checksums pass; no unreviewed dependencies |
| Tests | JVM, AOT, and native integration tests pass per release policy |
| Binary | Executable exists, matches target, SHA-256 recorded |
| SBOM | SBOM generated, parseable, and passes vulnerability/license policy |
| Provenance | Attestation has valid signature and matching subject digest |
| Container | Image scan passes, OCI digest recorded |
| Deployment | Policy verification passes; deployed via verified digest |

## 15. Reproducible Builds and What Rebuilding Proves

A reproducible build produces byte-for-byte identical artifacts given the same source, build instructions, and equivalent environment. This provides stronger verification than merely recording versions and checksums from a single build.

With Maven, you can configure a reproducible archive timestamp:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

The timestamp value must be managed consistently per release/build policy. Maven requires packaging plugins that support reproducible mode; you can test archive builds with:

~~~bash
./mvnw clean install
./mvnw clean verify artifact:compare
~~~

This check is useful for Maven artifacts like JARs, but does not automatically prove a GraalVM native executable is reproducible. For native binaries, rebuild in an independent yet identically pinned environment and compare SHA-256 digests directly.

Native Image can depend on OS image, compiler/linker, architecture, file paths, timestamps, PGO profiles, and other build inputs. Therefore:

- Pin the builder image by digest.
- Pin plugin and dependency versions.
- Fix build arguments and environment variables affecting output.
- Avoid reading unversioned files from the runner.
- Never use dynamic dependencies or `SNAPSHOT`s for releases.
- Record target architecture and libc baseline explicitly.
- Compare outputs of an independent rebuild before claiming reproducibility.

If two builds produce different checksums, it does not automatically mean the artifact was compromised; the build might simply not be reproducible yet. Compare provenance, build inputs, and environments to locate the source of divergence.

## 16. Promoting the Same Artifact Across Environments

A common mistake is building one binary for staging and rebuilding again for production. Two builds can yield different digests even from the same version and source commit.

A safer promotion workflow:

1. Build once from an approved commit.
2. Produce the binary, container image, SBOM, and provenance.
3. Run tests and scans against that exact digest.
4. Promote the exact same OCI digest through staging and production.
5. Vary runtime configuration via environment/secrets/config stores.
6. Never rebuild just to change environment-specific secrets or runtime endpoints.

If a Spring AOT profile or property changes the bean topology, it is a build-time input. When staging and production require different bean sets, produce separate artifact variants with distinct identities; never silently change a runtime property expecting AOT to regenerate bean definitions.

Deploy by digest:

~~~text
ghcr.io/acme/orders-service@sha256:<verified-image-digest>
~~~

Store a release record containing the source commit, build ID, binary digest, image digest, attestation reference, SBOM digest, target platform, and deployment environment.

## 17. Troubleshooting

| Symptom | Possible cause | Remediation |
|---|---|---|
| Same version, different binary digest | Toolchain, dependencies, build flags, or environment differed | Compare manifests/provenance of both builds |
| Sidecar checksum passes, but origin is unknown | Hash lacks a signature or trust anchor | Verify signed attestation and builder identity |
| Same Git commit, different output | Dirty working tree, submodule/LFS, or generated inputs differed | Check tree, clean state, and resolved dependencies |
| GraalVM upgrade changes the digest | Compiler/toolchain changed output | Record toolchain version, rebuild/test, and cut a new release |
| Gradle resolves different dependency versions between CI and local | Dependency locking not enabled | Commit lockfiles and enable `lockAllConfigurations` |
| Downloaded dependency has a different checksum | Artifact/cache/repository altered or bad metadata | Fail the build, inspect repository, and verify manually |
| Maven checksum policy only warns | Repository policy set to `warn` | Switch to `fail` per release policy |
| Provenance subject digest mismatches image | Attestation created for another tag or artifact | Attach attestation to the exact pushed digest |
| SBOM lacks build-time dependencies | Scanned only the final stage of a multi-stage image | Scan builder/context or generate a separate build-time SBOM |
| Image tag matches, but deployed bytes differ | Mutable tag was moved | Deploy and audit by OCI digest |
| Multi-arch release misses a platform | Only one architecture was built/tested | Build separate artifacts and verify each platform manifest |
| Build manifest contains secrets | Raw environment/build args logged | Strip secrets from metadata; use secret mounts and rotate exposed secrets |

## 18. Release Identification Checklist

- [ ] Service name, version, and unique build ID are present.
- [ ] Repository URI, full commit SHA, and Git tree SHA are recorded.
- [ ] Working tree is clean; submodule and Git LFS revisions are recorded.
- [ ] GraalVM builder image is pinned by digest.
- [ ] JDK, GraalVM, Native Image, compiler/linker, and Native Build Tools versions are recorded.
- [ ] Maven plugin/dependency versions are pinned or Gradle lock state is committed.
- [ ] Dependency verification metadata is reviewed and enforced in CI.
- [ ] Spring AOT profile, Native Image flags, `RuntimeHints`, and target platform are recorded.
- [ ] Build manifest contains no secrets.
- [ ] Native executable has a SHA-256 sidecar verified before publishing.
- [ ] SBOM covers runtime components and build-time materials per policy.
- [ ] Provenance attestation binds to the exact subject digest.
- [ ] Attestation signature and builder identity are verified.
- [ ] OCI image digest is stored and used for deployment.
- [ ] Multi-arch artifacts are built and tested separately per architecture.
- [ ] A release record links source, binary, image, SBOM, attestation, and deployment.

## 19. Self-Check Exercises

**Question 1.** Does the executable's SHA-256 prove the binary was built from an approved commit?

**Hint:** No. It identifies the bytes; signed provenance/attestation is needed to link the digest to source and builder.

**Question 2.** Why record both `native-image --version` and the builder image digest?

**Hint:** The version identifies the tool; the image digest pinpoints the exact builder filesystem and all packages/toolchains inside the image.

**Question 3.** How do Gradle dependency locking and dependency verification differ?

**Hint:** Locking pins resolved versions; verification checks checksums/signatures of downloaded artifacts.

**Question 4.** Why shouldn't `build-info.json` contain its own digest?

**Hint:** Self-referential digests create a cycle; generate the manifest after the artifact has its digest and keep the manifest checksum in a separate sidecar/attestation.

**Question 5.** Is a final container's SBOM guaranteed to include Maven/Gradle build dependencies?

**Hint:** No. Multi-stage builds can omit the builder stage from final image scans; collect build-time materials separately or configure scanning across stages/contexts.

**Question 6.** Why is deploying by OCI digest safer than relying solely on tags?

**Hint:** Tags can be moved; digests identify the exact verified manifest contents.

**Question 7.** If two builds from the same commit produce different native executable checksums, does that mean an attack occurred?

**Hint:** Not necessarily. Differences in toolchain, environment, or build inputs can cause it; compare provenance and test an independent rebuild.

## 20. References

- [SLSA — Build Provenance v1.2](https://slsa.dev/spec/v1.2/build-provenance): builders, build definitions, parameters, resolved dependencies, and artifact subjects.
- [SLSA — Verifying Artifacts](https://slsa.dev/spec/v1.2/verifying-artifacts): verifying signatures, builder identity, build types, and parameters.
- [in-toto — Attestation Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md): binding subject digests to predicates.
- [Docker — Build attestations](https://docs.docker.com/build/metadata/attestations/): SBOM/provenance attestations and how they attach to images.
- [Docker — Provenance attestations](https://docs.docker.com/build/metadata/attestations/slsa-provenance/): build parameters, materials, and SLSA provenance.
- [Docker — SBOM attestations](https://docs.docker.com/build/metadata/attestations/sbom/): SPDX SBOMs, final stage scanning, and build-time dependencies.
- [Gradle — Dependency verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum and signature verification.
- [Gradle — Dependency locking](https://docs.gradle.org/current/userguide/dependency_locking.html): pinning dependency versions.
- [Maven — Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html): reproducible archive timestamps and build comparison.
- [Maven — Settings reference](https://maven.apache.org/settings.html): checksum policies for repository artifacts.
- [GitHub — Artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations): generating and verifying provenance attestations for binaries/container images.

**Remember:** Native Image release identity must connect the source commit, toolchain, dependency graph, build configuration, target platform, and the exact output digest. SHA-256 verifies bytes; an SBOM inventories components; signed provenance ties the artifact to the build process. CI must verify all of this evidence before promoting the exact OCI digest through staging and production.
