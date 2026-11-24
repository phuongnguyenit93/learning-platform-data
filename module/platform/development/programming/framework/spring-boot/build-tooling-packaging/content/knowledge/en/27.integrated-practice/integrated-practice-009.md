# Completing CI to Produce Artifacts with Checksums, Metadata, and SBOMs for Traceability

A CI pipeline that only passes green tests and outputs a JAR file is not enough to answer critical questions at release time: **which commit built this file, with which JDK and dependency versions, which third-party components reside inside it, was the file altered in transit, and who can attest to the build process?** When a security incident occurs or a rollback is needed, lacking this data forces teams to dig through logs and guess which artifact was deployed.

This lesson builds a release workflow for a Spring Boot application consisting of interconnected evidence: **artifact**, **SHA-256 checksum**, **build metadata**, **Software Bill of Materials (SBOM)**, and **provenance attestation**. Examples use **Java 17, Spring Boot 3.3.13**, Maven or Gradle, the CycloneDX SBOM format, and an illustrative CI workflow. The result is an independently verifiable evidence bundle bound to the source commit and artifact digest, archived alongside the release.

**Distinguish from the start:** checksums detect bytes not matching a trusted digest; metadata describes the build; an SBOM lists components and dependency relationships; provenance/attestation supplies verifiable claims about where and how the artifact was created. Each answers a different question and none replaces the others.

## 1. Traceability Model from Source to Deployed Artifact

A release can be represented as a chain:

```text
Git commit + tag
       |
       v
CI workflow + trusted builder
       |
       +--> JDK / Maven or Gradle / plugin versions
       +--> resolved dependency graph
       |
       v
Spring Boot executable JAR/WAR
       |
       +--> SHA-256 checksum
       +--> build-metadata.json
       +--> SBOM (CycloneDX or SPDX)
       +--> signed provenance / attestation
       |
       v
Immutable artifact storage / release
       |
       v
Verify checksum + attestation + policy
       |
       v
Deploy the same artifact bytes
```

The goal is tracing backward from a running artifact: determine its digest, look up its attestation, inspect the commit/build invocation, read the SBOM for dependencies, and cross-check metadata for the toolchain.

**Build once, promote many:** build the artifact once in the release pipeline, verify it, then promote those exact bytes across staging/production. If each environment rebuilds from source, even with the same version string, artifacts can differ due to dependency resolution, JDK, plugins, timestamps, or build parameters. Checksums then only verify the bytes of each individual build, not that two environments run the same artifact.

## 2. Five Types of Evidence and the Questions Each Answers

| Component | What does it describe or prove? | Limitations |
| --- | --- | --- |
| **Artifact** | The actual file distributed, e.g., traceable-app-1.0.0.jar | Filename/version do not prove origin |
| **SHA-256 checksum** | Whether file bytes match the published digest | If an attacker replaces both file and checksum, comparison may still pass |
| **Build metadata** | Commit, version, JDK, build tool, workflow, timestamp, output file | Self-authored JSON does not prove trustworthiness on its own |
| **SBOM** | Components, versions, licenses, hashes, and dependency relationships | Does not prove where the artifact was built or that it is vulnerability-free |
| **Provenance/attestation** | Artifact digest bound to source, builder identity, and verifiable build process | Requires trusting the build platform, identity, and verification policy |

A checksum is not a digital signature. An SBOM is not a "zero vulnerabilities" report. Metadata is not signed provenance. Nor does attestation replace reviewing SBOMs or running security scans.

## 3. Choosing an SBOM Format: CycloneDX or SPDX?

An **SBOM** is a machine-readable inventory of software components that make up a product. For Java/Spring Boot, it typically describes the primary component, resolved direct/transitive dependencies, Package URLs (PURLs), versions, hashes, licenses, external references, and relationships among components.

Two widely adopted standards:

| Standard | Common strengths | When to use |
| --- | --- | --- |
| **CycloneDX** | Focused on inventory, dependency graphs, and security use cases; supports JSON/XML/Protocol Buffers | Component analysis, vulnerability management, and VEX |
| **SPDX** | Models packages, files, licenses, copyrights, and relationships; ISO/IEC 5962:2021 standard | License compliance and SPDX-based inventory exchange |

CycloneDX 1.7 is the standard version published by Ecma International in ECMA-424 2nd edition in December 2025. Examples below pin CycloneDX 1.6 so Maven/Gradle produce consistent, widely compatible outputs; the schema can be upgraded once consumers confirm support.

**Do not hand-write SBOM-like JSON and call it CycloneDX/SPDX.** Use plugins/tools that generate compliant schemas, then validate outputs with the corresponding parser/validator. Syntactically valid JSON is not guaranteed to be valid against the SBOM schema.

## 4. Java Dependency SBOM vs. Container Image SBOM

For a Spring Boot application running as an executable JAR, the SBOM from Maven/Gradle reflects the dependency graph resolved by the build tool: Spring Framework, Jackson, logging, database drivers, and other runtime libraries. Test scope is typically excluded from runtime inventory; provided scope may belong in the SBOM when those components are supplied by the deployment platform.

Shaded/relocated dependencies, manually copied libraries, generated binaries, or components omitted from the build graph may not be fully represented.

If packaging with Cloud Native Buildpacks or Docker:
- The image also contains **OS packages, base/run image layers, JVM runtime, and buildpack-provided components**.
- A Java dependency-graph SBOM does not automatically include all operating system packages of the final OCI image.
- Add a **container image SBOM** generated by a tool capable of inspecting the final image, and link the result to the image digest.

Clarify whether an SBOM describes a single module JAR, an entire multi-module distribution, an executable WAR, or an OCI image. For multi-module releases, only use an aggregate SBOM when it accurately reflects the exact set of packaged modules.

## 5. SHA-256 Checksum: Verifying Artifact Bytes

SHA-256 computes a 256-bit digest from file contents. The same file with the same algorithm yields the same digest; changing even a single byte almost certainly changes the digest.

On Linux/macOS:

```bash
sha256sum target/traceable-app-1.0.0.jar
```

Output shows a 64-character hex string followed by the filename. Actual digests must be computed from the freshly built artifact; never copy sample values into a release.

On Windows PowerShell:

```powershell
Get-FileHash .\target\traceable-app-1.0.0.jar -Algorithm SHA256
```

Output includes Hash and Algorithm fields. For downloaded files, compute the hash **after downloading** and compare it against the checksum obtained from a trusted source.

### 5.1. Manifest for multiple files

A release can include SHA256SUMS listing the artifact, SBOM, and metadata:

```bash
cd dist
sha256sum traceable-app-1.0.0.jar bom.json build-metadata.json > SHA256SUMS
sha256sum --check SHA256SUMS
```

When all files match, output looks like:

```text
traceable-app-1.0.0.jar: OK
bom.json: OK
build-metadata.json: OK
```

Run the verify command from the dist directory as shown because the manifest records relative filenames. If any file is altered, missing, or differs in bytes, sha256sum --check reports an error and exits non-zero.

### 5.2. Checksums alone are not tamper-proof

If both the artifact and SHA256SUMS are downloaded from the same untrusted website, an attacker can replace both. The comparison still succeeds, yet the recipient gets a forged artifact.

Therefore:
- Use checksums to detect corruption and verify files against a reference digest.
- Obtain digests from an authenticated channel or verify signatures/attestations backed by a trusted identity.
- Never use MD5 or SHA-1 as an integrity/security mechanism for new releases.
- If the artifact has provenance attestation, verify signer identity and subject digest against policy.

**Checksums answer "do the bytes match?"; signatures/attestations additionally answer "who attested to this digest and in which workflow?".**

## 6. Build Metadata: Recording How the Artifact Was Built

Metadata is a sidecar document, such as build-metadata.json, describing a single build. Useful fields:

| Group | Fields to record |
| --- | --- |
| Artifact | Filename, version, packaging type, media type, SHA-256 |
| Source | Repository URI, full commit SHA, tag/release, working tree status |
| Build invocation | Workflow/job, run ID, attempt, URL, start/end time |
| Toolchain | JDK vendor/version, Maven/Gradle Wrapper, Spring Boot/plugin versions, OS/architecture |
| Dependencies | SBOM path/digest, lockfile/verification metadata digest, dependency graph reference |
| Builder | CI platform identity, build container/builder image digest if applicable |
| Publication | Repository/package coordinates, registry, release ID, and digest after publish |

Use the **full Git commit SHA**, not just a branch name or short SHA. Branches can move; a commit SHA pinpoints exact source contents.

Metadata must never record passwords, access tokens, signing keys, secret environment variables, credentials from Maven settings.xml/Gradle properties, or full environment dumps. Only record an allowlist of fields needed for auditing.

If metadata contains checksums of the JAR and SBOM, generate it **after** those two files are finalized. Do not embed the checksum of build-metadata.json inside itself as that creates a self-referential dependency; include metadata in SHA256SUMS generated last.

## 7. Provenance and SLSA: Linking the Artifact to Source and Builder

**Provenance** is verifiable information about where, when, and how an artifact was produced. SLSA describes build provenance within the in-toto attestation framework.

Good build provenance typically links:
- **Subject:** the artifact and its digest.
- **Source dependency:** repository and exact commit.
- **Build definition:** build type, workflow, external parameters, and build instructions.
- **Builder identity:** trusted build platform that executed the process.
- **Resolved dependencies:** inputs fetched during the build, if recorded by the platform.
- **Run details:** invocation ID and start/end timestamps.

In SLSA/in-toto, provenance is a structured attestation; the subject digest binds the statement to the artifact's bytes. **Simply writing a JSON file named provenance.json does not establish trust**. You must use a build platform or signer with a verified identity, protect that identity, and verify attestations upon consuming the artifact.

SLSA v1.2 is the current version in the reference specifications at the time of writing. SLSA levels describe requirements on **build provenance and the build platform**, not an automatic quality badge for an SBOM. Having an SBOM does not imply a build meets a SLSA level.

## 8. Spring Boot Java 17 Project for Practicing Artifact Creation

Minimal layout:

```text
traceable-app/
├── pom.xml                         # Maven
├── settings.gradle                 # Gradle alternative to Maven
├── build.gradle                    # Gradle alternative to Maven
├── scripts/
│   └── create-evidence.sh
└── src/
    └── main/
        └── java/com/example/traceable/
            └── TraceabilityApplication.java
```

Maven and Gradle are two separate build options sharing the same Java code.

File src/main/java/com/example/traceable/TraceabilityApplication.java:

```java
package com.example.traceable;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class TraceabilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(TraceabilityApplication.class, args);
    }
}

@RestController
class TraceabilityController {

    @GetMapping("/health")
    String health() {
        return "traceable-app-ok";
    }
}
```

The package-private controller is still detected by Spring component scanning because it resides in the root package. When running on port 8080, HTTP GET /health returns:

```text
traceable-app-ok
```

This endpoint is a post-build smoke test for the JAR/image; it is not commit metadata. Commit and digest should live in sidecar/attestation artifacts to avoid conflating runtime info with build evidence.

## 9. Maven: POM with CycloneDX SBOM

The POM example uses Spring Boot 3.3.13 and CycloneDX Maven Plugin 2.9.3. Plugin 2.9.x generates CycloneDX schema 1.6; this aligns with the Gradle example below.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>traceable-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>

            <plugin>
                <groupId>org.cyclonedx</groupId>
                <artifactId>cyclonedx-maven-plugin</artifactId>
                <version>2.9.3</version>
                <configuration>
                    <projectType>application</projectType>
                    <schemaVersion>1.6</schemaVersion>
                    <outputFormat>json</outputFormat>
                    <outputName>bom</outputName>
                    <outputDirectory>${project.build.directory}</outputDirectory>
                    <includeCompileScope>true</includeCompileScope>
                    <includeProvidedScope>true</includeProvidedScope>
                    <includeRuntimeScope>true</includeRuntimeScope>
                    <includeTestScope>false</includeTestScope>
                </configuration>
                <executions>
                    <execution>
                        <id>generate-sbom</id>
                        <phase>package</phase>
                        <goals>
                            <goal>makeBom</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

The makeBom goal generates an SBOM for the Maven module. With this configuration, the JSON file is written to target/bom.json. includeProvidedScope=true retains provided-scope dependencies in the inventory; this is useful when a WAR application relies on an external Servlet container. Test scope is excluded so the SBOM focuses on application dependencies.

For multi-module Maven builds:
- makeBom builds per-module BOMs.
- makeAggregateBom builds an aggregated BOM at the reactor root.
- makePackageBom is for modules with war or ear packaging.

Choose the goal matching **what is released**. If the release artifact is a single module JAR, that module's BOM is usually appropriate. If the artifact is a distribution combining multiple modules, an aggregate BOM must describe the exact set of packaged modules.

## 10. Maven: Building the Artifact and SBOM

From the root directory:

```bash
java -version
./mvnw -B -ntp clean verify
```

If no Maven Wrapper is present, use a controlled installed Maven. With the POM in section 9, verify traverses the package phase, so the CycloneDX plugin runs via its declared execution.

Check outputs:

```bash
test -s target/traceable-app-1.0.0.jar
test -s target/bom.json
jar tf target/traceable-app-1.0.0.jar
```

Quick check of components in the SBOM:

```bash
grep -n '"bomFormat"' target/bom.json
grep -n '"components"' target/bom.json
```

The JSON output must indicate CycloneDX format and contain component data. grep is only a preliminary check; serious CI pipelines should use a CycloneDX validator or schema-aware parser.

Inspect the Maven dependency graph separately:

```bash
./mvnw -B dependency:tree -Dverbose \
    -DoutputFile=target/dependency-tree.txt
```

The dependency tree is supplementary evidence to investigate how Maven resolved versions; **the SBOM is the standardized inventory for cross-system exchange**. These two files serve different purposes and can be archived together with the release if deep investigation is needed.

## 11. Gradle: CycloneDX Plugin and Direct SBOM

The Gradle example uses Spring Boot 3.3.13, Java 17, and CycloneDX Gradle plugin 3.5.1. The 3.x plugin line requires **Gradle 8.4 or later**. If the project's wrapper is older, choose a compatible plugin version or upgrade the Gradle Wrapper with testing.

File settings.gradle:

```groovy
rootProject.name = 'traceable-app'
```

File build.gradle:

```groovy
import org.cyclonedx.Version
import org.cyclonedx.model.Component

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'org.cyclonedx.bom' version '3.5.1'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

springBoot {
    mainClass = 'com.example.traceable.TraceabilityApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('cyclonedxDirectBom') {
    projectType = Component.Type.APPLICATION
    schemaVersion = Version.VERSION_16
    includeConfigs = ['compileClasspath', 'runtimeClasspath']
    skipConfigs = ['(?i).*test.*']
}
```

cyclonedxDirectBom generates the SBOM for the current project. By default, the JSON output is written to build/reports/cyclonedx-direct/bom.json. Plugin 3.x also registers Direct SBOM tasks for subprojects when applied at the root. cyclonedxBom generates an **aggregate SBOM** from Direct SBOMs of enabled projects; only use aggregate when the artifact/distribution genuinely encompasses that set of projects.

Build:

```bash
./gradlew clean test bootJar cyclonedxDirectBom
```

Verify:

```bash
test -s build/libs/traceable-app-1.0.0.jar
test -s build/reports/cyclonedx-direct/bom.json
```

Dependency graph to aid investigation:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

With multi-module builds, you can generate an SBOM specifically for the app module using its project path task or create an aggregate at the root. Do not attach an aggregate SBOM to a standalone module JAR if the aggregate describes modules not present in that artifact; consumers will misunderstand the boundary.

## 12. Choosing the Right Dependency Scope in the SBOM

For an SBOM to be useful for security and compliance, understand which configurations/scopes the tool includes:

| Source | Include in runtime artifact SBOM? | Notes |
| --- | --- | --- |
| Compile/runtime dependencies | Yes | Typically direct or transitive components of the application |
| Maven provided / Gradle providedRuntime | Often yes when describing a WAR deployed to a container | Provided by the server at runtime, yet part of the deployment contract |
| Test-only dependencies | Typically no in runtime SBOM | A separate SBOM for test/build environments can be created if policy requires |
| Build plugins/build tools | May need a separate build-environment SBOM | Do not mix automatically into runtime SBOMs |
| OS packages/base image | Requires a separate image SBOM if releasing a container | Java dependency plugins do not fully describe OS layers |
| Manually copied/shaded dependencies | Requires additional verification | The build graph may not know they exist |

In Maven, includeCompileScope, includeProvidedScope, includeRuntimeScope, and includeTestScope control which scopes are captured. In Gradle plugin 3.x, includeConfigs and skipConfigs match configuration names via regex; for example, selecting compileClasspath and runtimeClasspath while skipping test configurations.

**Do not look only at component counts.** Verify that key dependencies have accurate versions, PURLs, and licenses; confirm expected modules are present; and verify test dependencies did not accidentally leak into the runtime SBOM if policy prohibits it.

## 13. Creating a Unified Evidence Bundle

After the build, a release directory can contain:

```text
dist/
├── traceable-app-1.0.0.jar
├── bom.json
├── build-metadata.json
└── SHA256SUMS
```

Roles:
- traceable-app-1.0.0.jar: the released artifact.
- bom.json: CycloneDX SBOM describing the artifact's dependencies.
- build-metadata.json: commit, toolchain, workflow, timestamp, and digests.
- SHA256SUMS: checksums for the artifact, SBOM, and metadata.

Provenance attestations may be stored outside this directory in the CI/registry attestation store, but must reference the **exact digest of the file in dist**. If saving attestations as separate files, also archive/verify them with their signature and identity mechanisms.

## 14. Bash Script to Generate Metadata and SHA256SUMS

Create scripts/create-evidence.sh:

```bash
#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_PATH="target/traceable-app-1.0.0.jar"
SBOM_PATH="target/bom.json"
BUILD_TOOL_NAME="Maven Wrapper"
SPRING_BOOT_VERSION="3.3.13"
SBOM_SPEC_VERSION="1.6"
DIST_DIR="dist"

test -s "$ARTIFACT_PATH"
test -s "$SBOM_PATH"

git diff --quiet
git diff --cached --quiet

mkdir -p "$DIST_DIR"

ARTIFACT_NAME="$(basename "$ARTIFACT_PATH")"
cp "$ARTIFACT_PATH" "$DIST_DIR/$ARTIFACT_NAME"
cp "$SBOM_PATH" "$DIST_DIR/bom.json"

ARTIFACT_SHA256="$(sha256sum "$DIST_DIR/$ARTIFACT_NAME" | awk '{print $1}')"
SBOM_SHA256="$(sha256sum "$DIST_DIR/bom.json" | awk '{print $1}')"

SOURCE_COMMIT="${GITHUB_SHA:-$(git rev-parse HEAD)}"
SOURCE_TAG="${GITHUB_REF_NAME:-$(git describe --tags --exact-match 2>/dev/null || true)}"
BUILD_ID="${GITHUB_RUN_ID:-local}"
BUILD_ATTEMPT="${GITHUB_RUN_ATTEMPT:-1}"
WORKFLOW_NAME="${GITHUB_WORKFLOW:-local}"
BUILD_TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
JAVA_VERSION="$(java -version 2>&1 | head -n 1)"
MAVEN_VERSION="$(./mvnw -version | head -n 1)"

BUILD_URL=""
if [[ -n "${GITHUB_SERVER_URL:-}" &&
      -n "${GITHUB_REPOSITORY:-}" &&
      -n "${GITHUB_RUN_ID:-}" ]]; then
    BUILD_URL="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
fi

jq -n \
    --arg artifact "$ARTIFACT_NAME" \
    --arg artifactSha256 "$ARTIFACT_SHA256" \
    --arg commit "$SOURCE_COMMIT" \
    --arg tag "$SOURCE_TAG" \
    --arg buildId "$BUILD_ID" \
    --arg buildAttempt "$BUILD_ATTEMPT" \
    --arg workflow "$WORKFLOW_NAME" \
    --arg buildUrl "$BUILD_URL" \
    --arg createdAt "$BUILD_TIMESTAMP" \
    --arg javaVersion "$JAVA_VERSION" \
    --arg mavenVersion "$MAVEN_VERSION" \
    --arg springBootVersion "$SPRING_BOOT_VERSION" \
    --arg buildTool "$BUILD_TOOL_NAME" \
    --arg sbomSha256 "$SBOM_SHA256" \
    --arg sbomSpecVersion "$SBOM_SPEC_VERSION" \
    '{
      schemaVersion: "1.0",
      artifact: {
        file: $artifact,
        mediaType: "application/java-archive",
        digest: {
          algorithm: "SHA-256",
          value: $artifactSha256
        }
      },
      source: {
        commit: $commit,
        tag: $tag
      },
      build: {
        id: $buildId,
        attempt: $buildAttempt,
        workflow: $workflow,
        url: $buildUrl,
        createdAt: $createdAt,
        tool: $buildTool,
        java: $javaVersion,
        maven: $mavenVersion,
        springBoot: $springBootVersion
      },
      sbom: {
        file: "bom.json",
        format: "CycloneDX JSON",
        specVersion: $sbomSpecVersion,
        digest: {
          algorithm: "SHA-256",
          value: $sbomSha256
        }
      }
    }' > "$DIST_DIR/build-metadata.json"

(
    cd "$DIST_DIR"
    sha256sum "$ARTIFACT_NAME" bom.json build-metadata.json > SHA256SUMS
    sha256sum --check SHA256SUMS
)
```

The script requires Bash, jq, sha256sum, Git, and Maven Wrapper. It fails if the artifact/SBOM is missing or if the tracked working tree has uncommitted changes. CI variables like GITHUB_SHA and GITHUB_RUN_ID are used in GitHub Actions; locally, the script reads the commit from Git and sets the build ID to local.

SHA256SUMS is generated **after** metadata, so the manifest covers all three files. Metadata stores the digests of the artifact and SBOM; the manifest additionally stores the digest of metadata. Do not include SHA256SUMS itself in the list it verifies.

If the project uses Gradle, replace ARTIFACT_PATH, SBOM_PATH, BUILD_TOOL_NAME, and MAVEN_VERSION in the script with the corresponding Gradle artifact, SBOM, and tool details. Do not keep a Maven version field for a Gradle build; record the actual Gradle Wrapper version.

## 15. Verifying Checksums on Windows PowerShell

On Windows, Get-FileHash can be used to recompute the digest:

```powershell
$artifact = ".\dist\traceable-app-1.0.0.jar"
$manifest = Get-Content ".\dist\SHA256SUMS"

$line = $manifest | Where-Object {
    $_ -match "traceable-app-1.0.0.jar$"
}

$expected = ($line -split "\s+")[0].ToLowerInvariant()
$actual = (Get-FileHash $artifact -Algorithm SHA256).Hash.ToLowerInvariant()

if ($actual -ne $expected) {
    throw "SHA-256 mismatch: artifact bytes do not match the manifest"
}

"SHA-256 verification: PASS"
```

Output when the file matches:

```text
SHA-256 verification: PASS
```

This checks the artifact JAR. The same check can be repeated for bom.json and build-metadata.json. If the manifest was fetched from the same untrusted source as the artifact, this check only detects transit corruption, not origin; independently verify signatures/attestations.

## 16. Reproducible Builds: Producing Identical Bytes from Identical Inputs

**Reproducible build** means identical source code, build environment, and build instructions produce byte-for-byte identical artifacts. This enables independent verification of artifacts, though a single build's checksum does not by itself prove reproducibility.

Sources of non-reproducible builds:
- Archive plugins writing timestamps or unstable file ordering.
- Dependencies using SNAPSHOTs, dynamic versions, or repositories allowing byte mutation.
- Differing Maven/Gradle Wrapper or JDK versions.
- Build scripts reading current time, hostname, username, or workspace paths.
- Generated files embedding timestamps or environment data.
- Mutable buildpack/base image tags.
- Downloaded dependencies lacking checksum/verification metadata.

### 16.1. Maven: fixing output timestamp to source revision

Maven supports project.build.outputTimestamp so archive plugins can create reproducible outputs. In CI, derive the commit timestamp:

```bash
SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"

./mvnw -B -ntp \
    -Dproject.build.outputTimestamp="$SOURCE_DATE_EPOCH" \
    clean verify
```

Building from the same source commit yields the same epoch value. Use plugin versions supporting reproducible archives; a timestamp property alone does not fix non-deterministic plugins or generated files.

Maven can compare two builds using the maven-artifact-plugin compare goal:

```bash
./mvnw clean install
./mvnw clean verify artifact:compare
```

This is a useful local check, though it does not prove a third party rebuilding in a completely independent environment gets identical bytes. Stronger verification builds in independent workspaces/containers and compares SHA-256 digests.

### 16.2. Gradle: archive ordering and file timestamps

In Groovy build.gradle:

```groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

In Kotlin build.gradle.kts:

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

This configuration standardizes timestamps and entry order for Gradle archive tasks. You still must pin toolchains, dependencies, and any plugins producing generated files.

### 16.3. Pinning dependencies and verifying input checksums

With Gradle:
- Enable dependency locking for relevant configurations.
- Run builds with --write-locks to generate/update lock state.
- Use dependency verification metadata to check checksums/signatures of downloaded dependencies.
- Commit gradle.lockfile and gradle/verification-metadata.xml per policy.

Example:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

```bash
./gradlew build --write-locks
./gradlew --write-verification-metadata sha256 help
./gradlew --dependency-verification=strict clean build
```

Review verification metadata files before committing. Do not blindly trust freshly collected checksums if dependency sources have not been validated; initial metadata creation must go through review.

With Maven:
- Use Spring Boot BOM/dependencyManagement to manage versions consistently.
- Disallow SNAPSHOT/dynamic versions in releases.
- Pin plugin versions and the Maven Wrapper.
- Consider Maven Enforcer to detect dependency convergence/unwanted versions.
- Ensure release repositories enforce immutability and verify artifact checksums.

## 17. Maven Wrapper and Gradle Wrapper Are Also Build Inputs

A pipeline can pin Java yet still fail to reproduce if different machines run different Maven/Gradle versions.

**Maven Wrapper:**
- Commit mvnw, mvnw.cmd, and .mvn/wrapper/.
- Pin the Maven distribution version in maven-wrapper.properties.
- Use distributionSha256Sum to verify the downloaded Maven archive.
- Record ./mvnw -version in build metadata.

**Gradle Wrapper:**
- Commit gradlew, gradlew.bat, and gradle/wrapper/.
- Pin distributionUrl and distributionSha256Sum.
- Do not use an arbitrary pre-installed Gradle on CI.
- Record ./gradlew --version in build metadata.

The JDK must also be pinned: major version alone is insufficient for strict needs; record vendor, patch/build, and architecture if they affect releases. Never dump credentials or secret values into metadata.

## 18. SBOM and Artifact Must Be Bound to the Same Release

A common process flaw is building a JAR from commit A, then generating an SBOM in a separate build or against a changed dependency graph. The result is two files carrying version 1.0.0 that do not describe the same build.

How to reduce risk:
1. Check out a specific commit SHA.
2. Resolve dependencies once in a single build invocation.
3. Build the artifact and SBOM from the same workspace and dependency graph.
4. Compute digests of the artifact and SBOM after both complete.
5. Record both digests in build metadata.
6. Create an attestation linking the artifact digest and SBOM together.
7. Store all three files in the same release bundle.

For multi-module projects, decide which SBOM describes the released artifact. Direct SBOMs for an app module and aggregate SBOMs for the entire reactor have different scopes; choosing the wrong boundary can mislead consumers into thinking components from test tooling or unshipped modules are runtime dependencies of the product.

## 19. GitHub Actions: Generating Artifact, SBOM, Checksum, and Attestations

Sample Maven workflow for release tags. File .github/workflows/release-evidence.yml:

```yaml
name: release-evidence

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read
  id-token: write
  attestations: write

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
          cache: maven

      - name: Build JAR and CycloneDX SBOM
        run: |
          SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
          ./mvnw -B -ntp \
            -Dproject.build.outputTimestamp="$SOURCE_DATE_EPOCH" \
            clean verify

      - name: Create metadata and checksum manifest
        run: bash scripts/create-evidence.sh

      - name: Attest artifact build provenance
        uses: actions/attest@v4
        with:
          subject-path: dist/traceable-app-1.0.0.jar

      - name: Attest artifact with its SBOM
        uses: actions/attest@v4
        with:
          subject-path: dist/traceable-app-1.0.0.jar
          sbom-path: dist/bom.json

      - name: Upload release evidence bundle
        uses: actions/upload-artifact@v4
        with:
          name: traceable-app-release-evidence
          path: dist/
          if-no-files-found: error
```

Key points:
- id-token: write allows the action to acquire an OIDC identity for creating attestations.
- attestations: write grants permission to write attestations.
- The provenance step runs on the JAR artifact after building.
- The SBOM attestation binds bom.json to the **exact same JAR artifact**.
- upload-artifact archives the bundle in the workflow run; this step does not by itself publish a release to a Maven repository or container registry.

In real workflows, synchronize artifact/version names between the POM and workflow. If the version changes with tags, pass the validated version into build scripts rather than hardcoding filenames in multiple places. Pin GitHub Actions by commit SHA per your organization's security policy; @v4 illustrates major version syntax, not an immutable pin.

GitHub artifact attestations require specific permissions and availability depending on repository/plan type. On other CI systems, use an equivalent platform generating in-toto/SLSA provenance; **do not treat GitHub Actions as mandatory for the traceability model**.

## 20. Verifying the Artifact and Attestation Before Deployment

The recipient downloads the artifact along with its evidence bundle and performs:

**Step 1 — verify checksums:**

```bash
cd dist
sha256sum --check SHA256SUMS
```

**Step 2 — verify provenance attestation:**

```bash
gh attestation verify traceable-app-1.0.0.jar \
    -R "$GITHUB_REPOSITORY"
```

**Step 3 — verify SBOM attestation:**

```bash
gh attestation verify traceable-app-1.0.0.jar \
    -R "$GITHUB_REPOSITORY" \
    --predicate-type https://cyclonedx.org/bom
```

The gh attestation verify commands require a GitHub CLI supporting attestations and access to the corresponding repository. Check output for signer/workflow identity, repository, source ref, and subject digest against policy. A command returning success alone is insufficient if policy does not enforce **allowed identities**, allowed commits/tags, and approved workflows.

**Step 4 — inspect metadata/SBOM contents:**
- Do the artifact filename/version match the release?
- Does the SHA-256 in metadata match the checksum and subject digest?
- Does the commit SHA match the release tag?
- Are the build workflow, JDK, Spring Boot, and dependency versions within policy?
- Does the SBOM match the expected format/schema and primary component?
- Have dependency/license/vulnerability findings been evaluated against organizational criteria?

If any required condition fails, halt promotion/deployment and investigate. Never manually edit metadata just to make checksums match; regenerate evidence from a controlled build.

## 21. Container Image Artifacts Need Separate Digests

If the pipeline also publishes an OCI image:
- A tag like registry.example/team/traceable-app:1.0.0 is a mutable label.
- The registry manifest digest sha256:... identifies the manifest contents.
- docker image inspect --format '{{.Id}}' returns the local image ID/config identity, not automatically the registry manifest digest.
- After pushing, capture the digest from registry/build tool output and store it in metadata/provenance.
- The Java dependencies SBOM and the final container image SBOM may be two distinct inventories.

An attestation for a container image must bind to **image name + digest**, not just the tag. When deploying, use the immutable digest if supported by the platform; do not rebuild a different image while reusing the release tag.

With Buildpacks, the image SBOM should account for base/run images and OS components. If attaching only bom.json generated by Maven, clearly document that it is the SBOM of Java project dependencies and do not claim it covers all packages in the final image.

## 22. Storing and Distributing the Evidence Bundle

Store artifacts and evidence side by side:
- Maven repository: JAR/WAR, SBOM classifier or sidecar, checksums/signatures per repository policy.
- GitHub/GitLab release: artifact file, bom.json, build-metadata.json, SHA256SUMS.
- OCI registry: image digest, image SBOM, and attestations linked to the digest.
- Internal artifact repository: keep build logs, dependency lock/verification files, and provenance alongside the release record.

Use immutable version coordinates and appropriate retention. Never overwrite 1.0.0 with different bytes. If a release fix is needed, publish a new version and keep links to the old version for audit/rollback.

A directory layout that can be archived:

```text
release-1.0.0/
├── traceable-app-1.0.0.jar
├── bom.json
├── build-metadata.json
├── SHA256SUMS
└── attestations/
    ├── build-provenance
    └── sbom-attestation
```

If the platform manages attestations outside the filesystem, the directory may store only reference URIs/IDs. What matters is that recipients can retrieve and verify attestations by subject digest.

## 23. Common Errors When Generating Checksums, Metadata, and SBOMs

| Symptom | Cause | Fix |
| --- | --- | --- |
| Checksum changes on every build despite unchanged code | Archive timestamps, plugin output, environment leaks, or changing dependencies | Enable reproducible archive settings, pin inputs, and compare two builds |
| Downloaded file checksum does not match | File corruption, wrong version, or altered file | Re-download from trusted source, check digest and attestation |
| Both artifact and checksum were tampered with yet verification passes | Both fetched from one untrusted source | Verify signatures/attestations with a trusted identity |
| bom.json does not exist | Plugin did not run or different output path | Check Maven phase/Gradle task and build logs |
| SBOM missing runtime dependency | Scope/configuration excluded | Check includeCompile/Runtime/Provided or Gradle includeConfigs |
| SBOM contains test libraries | Test scope/configuration included | Adjust scope filters and document SBOM boundary |
| WAR SBOM missing Servlet container | Provided scope excluded | Include provided components in SBOM per deployment contract |
| SBOM missing OS packages | Generated only from Java dependency graph | Also generate an image SBOM from the final OCI image |
| Multi-module SBOM missing projects | Only generated Direct SBOM for one module | Use aggregate when artifact truly includes those modules |
| SBOM schema rejected by scanner | Incompatible CycloneDX/SPDX version | Pin schema version per consumer and validate before release |
| Metadata commit does not match source tag | Built from moving branch or checked out wrong SHA | Check out full commit SHA and verify tag/revision |
| Metadata records wrong JDK | CI used different JDK than local or did not record actual runtime | Capture java -version, toolchain/vendor, and build logs |
| Provenance verification fails | Attestation subject digest differs from artifact or untrusted signer | Compare digests, workflow identity, and source claims |
| SBOM attestation verification fails | SBOM not bound to artifact or wrong predicate type | Generate attestation with exact artifact + SBOM paths and verify predicate |
| Metadata missing build URL | CI did not pass run ID/URL | Map build platform variables into metadata script |
| Artifact rebuilt during deployment | Promotion pipeline triggered another build | Promote the exact tested artifact |
| Release tag overwritten | Registry/repository allows mutable versions | Enforce immutable release policy and digests |
| Metadata script leaks secrets | Dumped full environment or credentials | Select allowlist fields only, review output before publishing |
| Checksum manifest cannot find files | Ran sha256sum --check from wrong directory | Run from dist or use manifest with matching relative paths |

## 24. Incident Response Workflow When Traceability Is Incomplete

When discovering an artifact missing checksum/SBOM or failing provenance verification:

1. Identify the exact artifact in question: filename, version, repository coordinates, or image digest.
2. Recompute SHA-256 from the bytes on hand; do not infer from the tag.
3. Locate the SHA256SUMS and metadata released with the artifact.
4. Verify attestations against the subject digest and trusted builder identity.
5. Cross-check commit, tag, workflow run, and toolchain.
6. Inspect SBOM schema, primary component, resolved versions, and dependency scopes.
7. If evidence is missing or mismatched, hold the artifact from promotion; do not generate a fresh checksum and treat it as original build evidence.
8. If rebuilding is required, create a new release/evidence bundle and record the new artifact digest.
9. If already deployed, determine which image digest/artifact digest workloads are running before rolling back.
10. Save investigation logs and update the pipeline so similar gaps are blocked in future releases.

**Never manually edit checksums/metadata to hide a mismatch.** If artifact bytes changed, treat it as a different artifact with a new digest and new provenance.

## 25. Pre-Release CI Checklist

- [ ] Checked out source by full commit SHA and identified release tag.
- [ ] Clean working tree; build inputs and build scripts reviewed.
- [ ] Java, Spring Boot, Maven/Gradle Wrapper, and plugin versions pinned.
- [ ] Dependencies have appropriate lock/verification or version management; releases do not use out-of-policy SNAPSHOT/dynamic versions.
- [ ] Unit/integration tests and security checks completed.
- [ ] JAR/WAR artifact built once from a single build invocation.
- [ ] CycloneDX/SPDX SBOM generated from the resolved dependency graph and accurate boundary.
- [ ] Provided/runtime/test scopes selected intentionally.
- [ ] Container image has its own SBOM when OS/base image inventory is needed.
- [ ] Artifact SHA-256 computed after the file is finalized.
- [ ] build-metadata.json records source commit, workflow ID, toolchain, timestamp, and artifact/SBOM digests.
- [ ] SHA256SUMS covers artifact, SBOM, and metadata.
- [ ] Manifest verified in CI before uploading.
- [ ] Provenance/attestation created by trusted build platform, bound to the exact artifact digest.
- [ ] SBOM attestation binds SBOM to the exact same artifact subject.
- [ ] Workflow identity, source revision, builder, and invocation verified against policy.
- [ ] Artifact/evidence stored in an immutable release repository.
- [ ] Promotion/deployment uses the exact tested artifact bytes or OCI digest.
- [ ] Retention and rollback records exist for the release.
- [ ] No secrets in metadata, checksum files, or build logs.

**Remember:** checksums tell you whether bytes match a digest; metadata tells you what the build declared; SBOMs list components; provenance/attestations tie the artifact digest to a verifiable source and builder. A complete pipeline generates all evidence from **the same build invocation**, stores it beside the release, verifies it before promotion, and deploys the exact approved bytes.

## Official References

- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [CycloneDX Maven Plugin — Documentation](https://cyclonedx.github.io/cyclonedx-maven-plugin/)
- [CycloneDX Maven Plugin — Releases](https://github.com/CycloneDX/cyclonedx-maven-plugin/releases)
- [CycloneDX Gradle Plugin — Documentation](https://github.com/CycloneDX/cyclonedx-gradle-plugin)
- [Gradle Plugin Portal — CycloneDX Plugin](https://plugins.gradle.org/plugin/org.cyclonedx.bom)
- [CycloneDX — Specification Overview](https://cyclonedx.org/specification/overview/)
- [Ecma International — ECMA-424 CycloneDX](https://ecma-international.org/publications-and-standards/standards/ecma-424/)
- [SPDX — Specification](https://spdx.github.io/spdx-spec/)
- [SLSA v1.2 — Provenance](https://slsa.dev/spec/v1.2/provenance)
- [SLSA — Build Provenance](https://slsa.dev/spec/v1.2/build-provenance)
- [GitHub Docs — Artifact Attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
- [GitHub Docs — Generate Artifact Attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
- [GitHub Docs — Verify Artifact Attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations)