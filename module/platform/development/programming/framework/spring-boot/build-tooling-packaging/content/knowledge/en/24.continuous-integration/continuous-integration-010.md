# Attaching Checksums, SBOMs, and Metadata to CI Outputs for Spring Boot

## 1. Goal: Every Build Must Ship an Evidence Bundle Alongside the Artifact

A CI pipeline should not return only a `BUILD SUCCESS` line and a JAR file. Artifact recipients must be able to answer:

- **Which exact file is this artifact?** What are its name, version, format, size, and SHA-256?
- **Which source built it?** Which Git repository, commit, ref/tag, and build run?
- **Which software components does it contain?** What are its direct/transitive dependencies, versions, package URLs (PURLs), dependency relationships, and licenses in the SBOM?
- **Which image was published?** Where are the registry, immutable digest, builder/base image, and image SBOM?
- **Who or what attests to the result?** How can checksums, signatures, and build provenance be verified?
- **How long does CI retain results, who can download them, and how are they re-verified after download?**

A **release evidence bundle** should accompany the JAR/WAR or container image:

~~~text
release-evidence/
├── release-demo.jar
├── application-sbom.cdx.json
├── image-sbom.cdx.json             # if an OCI image exists
├── build-metadata.json
├── SHA256SUMS
├── SHA256SUMS.sigstore.json        # if signing the checksum manifest
├── provenance.intoto.jsonl        # if CI emits provenance
└── buildx-metadata.json            # if using Docker Buildx
~~~

Filenames are illustrative. Not every project requires every file; **the JAR, matching SBOM, metadata, and checksums** form a practical minimum. For container deliverables, add the image digest and an SBOM scanned from the built image. Signatures and provenance are added whenever release policy requires them.

This lesson uses **Java 17 and Spring Boot 3.3.13**, demonstrating Maven and Gradle, **CycloneDX 1.6** SBOMs, SHA-256, GitHub Actions, Syft, and Cosign. These serve as a runnable reference set; pin plugin and tool versions approved by your organization and check compatibility with your current build tools. Commands below are instructions, not captured CI run outputs.

## 2. Distinguishing Four Types of Evidence

| Component | Question It Answers | What Does It Not Prove? |
| --- | --- | --- |
| **Checksum (SHA-256)** | Do the file's current bytes match the bytes when the checksum was generated? | Does not prove who created the file or that its source is trustworthy. |
| **SBOM** | Which software components are inside the described artifact/image? | Does not prove the artifact was vulnerability-scanned or that every component was detected. |
| **Build metadata** | What are the source commit, build run, toolchain, artifact paths/digests, and build details? | A self-generated JSON file does not prove the metadata is accurate or signed. |
| **Build provenance / attestation** | Which trusted builder produced which artifact, from which inputs and process? | Does not replace signature verification, trust policies, or SBOM/vulnerability checks. |

### 2.1. Checksums Verify Byte Integrity

SHA-256 takes file bytes and outputs a 256-bit digest (64 hex characters). If a single byte in the JAR changes, the digest changes almost certainly.

Checksums detect files corrupted during upload/download/copy, files altered after evidence generation, wrong files/versions downloaded, or copies stored in two places with differing bytes.

However, if an attacker can replace both the JAR **and** `SHA256SUMS`, they can generate a matching new checksum. Therefore, the checksum manifest must be protected by **a trusted signature/attestation**, or distributed via an integrity-protected channel with authenticated identity.

### 2.2. SBOMs Are Software Component Inventories

A **Software Bill of Materials (SBOM)** inventories the components of a software deliverable. For Java apps, an SBOM describes the root component (group/name/version), direct and transitive dependencies, resolved versions after conflict resolution/constraints, PURLs, suppliers, licenses, external references, and the dependency graph when metadata is available.

SBOMs support inventory tracking, license reviews, tracing dependencies affected by newly disclosed CVEs, and sharing supply-chain data with artifact consumers. **An SBOM is not a vulnerability report:** run a dedicated SCA/vulnerability scanner and record the scanner/database version, scan time, policy, and findings.

### 2.3. Build Metadata Enables Tracing Back to the Build

Metadata is typically JSON or properties recording:

- Repository and full commit SHA.
- Branch/tag/ref and build run ID/URL.
- Java/JDK, Maven/Gradle Wrapper, Spring Boot, and plugin versions.
- Artifact filename, size, and SHA-256.
- SBOM format/schema, filename, and SHA-256.
- Image reference **by digest**, plus builder/base image where applicable.
- Build start/finish timestamps and builder identity.

Metadata must be **non-secret**. Never record access tokens, private URLs with credentials, full environment dumps, passwords, signing private keys, or command lines containing secrets.

### 2.4. Provenance Is Verifiable Attestation

**SLSA build provenance** describes output artifacts, builders, build types, input parameters, and resolved dependencies in a structured format. Provenance is generated by a **trusted build platform**, bound to output digests, and cryptographically verifiable.

A self-written `build-metadata.json` helps humans and pipelines, yet **is not automatically SLSA provenance**. Never label a self-declared JSON file with a SLSA level; SLSA levels depend on the build platform's security properties and isolation guarantees.

## 3. Overall Pipeline and Evidence Generation Order

~~~text
Checkout source + record commit
           |
           v
Compile / Test / Package
           |
           +--> Spring Boot build-info (non-secret, optional)
           |
           v
Generate CycloneDX SBOM for application dependencies
           |
           v
Validate artifact + SBOM outputs
           |
           v
SHA-256 application JAR + SBOM
           |
           v
Build image (if the deliverable is an OCI image)
           |
           +--> Resolve immutable image digest
           +--> Generate image SBOM from that digest
           |
           v
Write build-metadata.json
           |
           v
Generate SHA256SUMS for final evidence files
           |
           v
Sign checksum manifest / image / attest provenance
           |
           v
Upload immutable CI artifact + retention policy
           |
           v
Consumer downloads → verifies signature → checks SHA-256 → reviews SBOM
~~~

**Why must checksums be generated after packaging?** If the JAR is later repackaged, resource-filtered, or modified after hashing, the recorded checksum no longer describes the final artifact.

**Why is metadata generated after SBOM/image creation?** That lets metadata record the digests of the final JAR, SBOM, and image deliverables. `SHA256SUMS` is generated last to cover the JAR, SBOM, and metadata; never include `SHA256SUMS` itself inside its own list (avoiding circular hashing).

## 4. Spring Boot build-info: Lightweight Metadata Inside the JAR

Spring Boot can generate `META-INF/build-info.properties` so the app/Actuator displays build coordinates and supplementary details. This is **in-archive metadata**; it does not replace external metadata files containing checksums and SBOMs.

### 4.1. Maven build-info

Add this execution to your existing `spring-boot-maven-plugin` configuration:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>build-info</id>
            <goals>
                <goal>build-info</goal>
            </goals>
            <configuration>
                <additionalProperties>
                    <java.version>${java.version}</java.version>
                </additionalProperties>
                <excludeInfoProperties>
                    <excludeInfoProperty>time</excludeInfoProperty>
                </excludeInfoProperties>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

This is a **plugin fragment to merge into your POM**, not a replacement for the entire plugin configuration. The Spring Boot Maven Plugin writes the file to `target/classes/META-INF/build-info.properties` so it gets packaged into the JAR.

- `group`, `artifact`, `name`, and `version` describe project coordinates.
- `additionalProperties` appends non-sensitive fields like Java version.
- Exclude `time` when prioritizing reproducible builds: changing timestamps change JAR bytes even when source and dependencies stay identical.
- If exact build timestamps are required, keep `time` and record it in metadata while accepting that archive bytes may differ across builds.

When Actuator is configured to expose build information, `BuildProperties` appears in the `info` endpoint. **Never expose internal build metadata endpoints publicly** if policy forbids revealing versions, commits, or internal references.

### 4.2. Gradle bootBuildInfo

In `build.gradle` Groovy DSL:

~~~groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
~~~

The Spring Boot Gradle Plugin provides the `bootBuildInfo` task, generating `META-INF/build-info.properties` for inclusion in the Boot JAR. Run:

~~~bash
./gradlew clean test bootBuildInfo bootJar
~~~

To add extra properties, use `properties.additional` with non-secret values. Never put tokens, credentialed URLs, or private keys into `buildInfo`. If the build JVM differs from the compiling Java toolchain, record **build JDK** and **Java target/toolchain** separately in metadata to avoid confusion.

### 4.3. Why Is build-metadata.json Still Necessary?

`build-info` inside the JAR usually contains only project coordinates and a few properties. It generally lacks the JAR's own SHA-256, SBOM/image digests, CI run URL/identity, builder ID, full resolved inputs, signatures, and independently verifiable provenance.

Use `build-info` for runtime app identification and **external metadata** for release evidence.

## 5. Maven: Generating a CycloneDX SBOM for Spring Boot

### 5.1. Configuring the Plugin

The example below uses `cyclonedx-maven-plugin` version `2.9.1`, supporting CycloneDX 1.6. Add the plugin under `build/plugins` in the POM:

~~~xml
<plugin>
    <groupId>org.cyclonedx</groupId>
    <artifactId>cyclonedx-maven-plugin</artifactId>
    <version>2.9.1</version>
    <executions>
        <execution>
            <id>generate-sbom</id>
            <phase>verify</phase>
            <goals>
                <goal>makeBom</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <projectType>application</projectType>
        <schemaVersion>1.6</schemaVersion>
        <outputFormat>all</outputFormat>
        <outputName>bom</outputName>
        <includeBomSerialNumber>true</includeBomSerialNumber>
        <includeCompileScope>true</includeCompileScope>
        <includeRuntimeScope>true</includeRuntimeScope>
        <includeProvidedScope>false</includeProvidedScope>
        <includeSystemScope>false</includeSystemScope>
        <includeTestScope>false</includeTestScope>
        <includeLicenseText>false</includeLicenseText>
    </configuration>
</plugin>
~~~

Explanation:

- `makeBom` generates a BOM for the current Maven module.
- `projectType=application` marks the root component as an application.
- `schemaVersion=1.6` selects the CycloneDX schema; downstream scanners must support this version.
- `outputFormat=all` outputs both JSON and XML.
- `outputName=bom` with the default `target` output directory yields `target/bom.json` and `target/bom.xml`.
- `includeCompileScope`/`includeRuntimeScope` retain application dependencies; `provided`, `system`, and `test` are omitted in this runtime-focused example. Adjust scopes to match how your project actually packages and ships dependencies.
- The BOM serial number identifies the document; it is **not a checksum or signature**.

`makeBom` fits single-module SBOMs. For multi-module Maven builds, use `makeAggregateBom` at the root if the released artifact represents **the entire reactor**; you can also emit per-module BOMs. Never attach a whole-monorepo aggregate SBOM to a single sub-JAR if it describes far more components than that artifact ships.

### 5.2. Running the Build and Verifying Outputs

With the Maven Wrapper:

~~~bash
./mvnw --batch-mode clean verify
test -s target/release-demo.jar
test -s target/bom.json
test -s target/bom.xml
~~~

Set `finalName` to `release-demo` in the `build` section if you want the executable JAR at `target/release-demo.jar`. Otherwise use the exact filename Maven emits; never mistake `.jar.original` for the executable Boot archive.

Verify JSON parsing and schema declaration with `jq`:

~~~bash
jq -e '.bomFormat == "CycloneDX" and .specVersion == "1.6"' target/bom.json
~~~

Success prints `true` (or the evaluated expression) with exit code 0; if parsing or the schema declaration fails, the job must fail or trigger investigation. Checking JSON syntax **does not replace** schema validation using CycloneDX CLI or a consumer validator.

### 5.3. SBOM Scopes and Multi-Module Builds

The Maven plugin can model compile, provided, runtime, system, and test scopes. The SBOM must reflect **the exact product boundary**:

- For executable Boot JARs, runtime dependencies matter most.
- Test libraries do not belong in regular runtime deliverables.
- `provided` dependencies supplied by the runtime environment should still be tracked in a separate SBOM if supply-chain policies require it.
- Multi-module applications should produce an aggregate SBOM for the full product or per-component SBOMs alongside an aggregate, depending on release layout.

Never strip a dependency from an SBOM arbitrarily just to quiet alerts; if a component ships in the product, keep it traceable.

## 6. Gradle: Generating a CycloneDX SBOM

### 6.1. Configuring the Plugin

Groovy DSL example using `org.cyclonedx.bom` version `3.4.0`. Plugin 3.x requires Gradle 8.4 or newer; check Gradle Wrapper compatibility with your Spring Boot plugin version.

In `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
    id 'org.cyclonedx.bom' version '3.4.0'
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
    implementation 'org.apache.commons:commons-lang3:3.14.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'release-demo.jar'
}

tasks.cyclonedxDirectBom {
    projectType = 'application'
    includeConfigs = ['runtimeClasspath']
    skipConfigs = ['(?i).*test.*']
}
~~~

This is a complete build file for a demo project; add your application's actual dependencies. In real projects, pin Spring Boot, Gradle, and plugin versions per your compatibility matrix and verify the Gradle Wrapper version:

~~~bash
./gradlew --version
~~~

### 6.2. Running Tasks and Output Paths

For a single module:

~~~bash
./gradlew clean test bootBuildInfo bootJar cyclonedxDirectBom
test -s build/libs/release-demo.jar
test -s build/reports/cyclonedx-direct/bom.json
~~~

The CycloneDX Gradle plugin outputs Direct SBOMs to `build/reports/cyclonedx-direct/bom.json` and `.xml` by default. `includeConfigs=['runtimeClasspath']` selects the runtime classpath configuration; `skipConfigs` excludes test configurations via full-name regex matching. `includeConfigs` and `skipConfigs` match configuration names, not dependency names.

In multi-project builds:

- `cyclonedxDirectBom` generates a per-project SBOM.
- `cyclonedxBom` generates a root Aggregate SBOM from enabled Direct SBOMs.
- Attach an aggregate BOM to a release artifact only if the aggregate matches the exact subprojects forming that deliverable.

When customizing Direct SBOM settings across multiple subprojects, apply rules consistently to every project contributing to the aggregate; do not assume root-level settings propagate automatically to every subproject.

### 6.3. Verifying Schema Declaration

~~~bash
jq -e '.bomFormat == "CycloneDX" and .specVersion == "1.6"' build/reports/cyclonedx-direct/bom.json
~~~

Plugin 3.x supports schema 1.7 via `schemaVersion` if consumers support it. Do not upgrade schema versions solely because a newer spec exists; verify your consumer's SBOM intake service, scanner, and policy engine first.

## 7. JAR SBOMs and OCI Image SBOMs Are Not the Same

The CycloneDX Maven/Gradle plugin describes the project's dependency graph according to the build tool. It works well for JARs/WARs, yet **does not automatically capture every package in the final container image**.

| SBOM | Scope | Typical Generation Method |
| --- | --- | --- |
| Application/project SBOM | Project coordinates and Maven/Gradle dependency graph | CycloneDX Maven/Gradle plugin |
| Binary/archive SBOM | Components identified inside the actual JAR/WAR/ZIP | Archive-aware scanner, optionally paired with project SBOM |
| Container image SBOM | App files, JRE, OS packages, libraries, and components in the OCI image | Image scanner such as Syft after building the image |
| Build environment SBOM | Toolchains, build dependencies, builder images | Separate inventory for builders/environments if required by policy |

A JAR might declare Spring Web and Commons Lang; the final Paketo/Docker image also adds a Java runtime, OS libraries, CA certificates, and OS packages. Uploading only the project SBOM does **not allow consumers to claim they inventoried the entire image**.

### 7.1. Generating an Image SBOM with Syft

After publishing the image, resolve its **immutable digest** (not just its tag):

~~~bash
IMAGE_REF_DIGEST=registry.example.invalid/team/release-demo@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef

syft "$IMAGE_REF_DIGEST" \
  -o cyclonedx-json=dist/release-evidence/image-sbom.cdx.json
~~~

`registry.example.invalid` and the digest above are format examples, not a real image. Substitute the digest returned by your registry/build tool. When authenticating to a registry, supply pull credentials via a secret store—never embed passwords in command lines or logs.

Syft can emit CycloneDX JSON/XML and other formats. Check scanner versions and format/schema compatibility before handing SBOMs to consumers. For multi-architecture images, record the platform/manifest digest and scan the exact manifest/platform production runs.

### 7.2. Tags Differ from Digests

A tag like `release-demo:1.0.0` can be moved to another image. The digest `sha256:...` pins specific manifest content. Metadata should record:

~~~json
{
  "image": {
    "tag": "registry.example.invalid/team/release-demo:1.0.0",
    "digest": "sha256:...",
    "immutableReference": "registry.example.invalid/team/release-demo@sha256:..."
  }
}
~~~

This structure is illustrative; populate real values from the registry. **Never read `docker image inspect .Id` and call it a manifest digest:** image config IDs and registry manifest digests are distinct digests. Capture the digest from push output, Buildx metadata, or the appropriate registry API.

## 8. Creating a SHA-256 Manifest for the Artifact and SBOM

### 8.1. Preparing an Evidence Directory

For Maven, after `clean verify` and CycloneDX generation:

~~~bash
mkdir -p dist/release-evidence
cp target/release-demo.jar dist/release-evidence/
cp target/bom.json dist/release-evidence/application-sbom.cdx.json
~~~

For Gradle, swap the two copy sources for:

~~~bash
mkdir -p dist/release-evidence
cp build/libs/release-demo.jar dist/release-evidence/
cp build/reports/cyclonedx-direct/bom.json \
  dist/release-evidence/application-sbom.cdx.json
~~~

If distributing XML as well, copy the `.xml` file too. Never copy `target/`, `build/`, `.gradle/`, `.m2/`, `.env`, settings credentials, or the whole workspace into the evidence bundle.

### 8.2. Generating the Manifest with GNU sha256sum

Run from the project root:

~~~bash
(
  cd dist/release-evidence
  sha256sum release-demo.jar application-sbom.cdx.json > SHA256SUMS
  sha256sum --check SHA256SUMS
)
~~~

Example output when files match:

~~~text
release-demo.jar: OK
application-sbom.cdx.json: OK
~~~

This is verification output, not a specific digest. `SHA256SUMS` holds the real digests and relative paths of the two files. Recipients must run verification **inside that same evidence directory** so relative paths match.

Once `build-metadata.json` is created, include it in the manifest:

~~~bash
(
  cd dist/release-evidence
  sha256sum release-demo.jar application-sbom.cdx.json build-metadata.json > SHA256SUMS
  sha256sum --check SHA256SUMS
)
~~~

If `image-sbom.cdx.json` exists, include it in the list as well. When signing the checksum manifest, sign **after the manifest is finalized**; never edit the manifest after signing.

### 8.3. Verifying on Windows PowerShell

PowerShell computes hashes via:

~~~powershell
Get-FileHash .\dist\release-evidence\release-demo.jar -Algorithm SHA256
Get-FileHash .\dist\release-evidence\application-sbom.cdx.json -Algorithm SHA256
~~~

To check against an expected digest read from a manifest:

~~~powershell
$expected = "PUT_THE_EXPECTED_64_HEX_DIGEST_HERE"
$actual = (Get-FileHash .\dist\release-evidence\release-demo.jar -Algorithm SHA256).Hash.ToLowerInvariant()

if ($actual -ne $expected.ToLowerInvariant()) {
    throw "SHA-256 mismatch for release-demo.jar"
}
"SHA-256 verified"
~~~

`PUT_THE_EXPECTED_64_HEX_DIGEST_HERE` is a checksum sourced from a trusted manifest, not a secret or default constant. In automation, parse the corresponding line of `SHA256SUMS` and compare programmatically rather than copying manually.

### 8.4. Verifying After Download

Recipients should download the artifact and full evidence bundle from the same release/run; verify the signature on `SHA256SUMS` if present; run `sha256sum --check SHA256SUMS`; confirm the JAR/SBOM filenames in the manifest match the deliverable under review; read metadata and cross-check commit, build ID, and image digest; and only then use or deploy the artifact.

**Never trust a checksum manifest solely because it sits next to the JAR.** Unless signed, the manifest can be altered alongside the artifact.

## 9. Generating build-metadata.json Outside the Archive

### 9.1. Recommended Metadata Structure

~~~json
{
  "schemaVersion": 1,
  "source": {
    "repository": "example-org/release-demo",
    "commit": "40-hex-character-git-commit",
    "ref": "refs/tags/v1.0.0"
  },
  "build": {
    "id": "ci-run-12345",
    "url": "https://ci.example.invalid/runs/12345",
    "tool": "Maven",
    "toolVersion": "3.9.x",
    "javaVersion": "17",
    "springBootVersion": "3.3.13"
  },
  "artifacts": [
    {
      "role": "application",
      "file": "release-demo.jar",
      "sha256": "64-hex-character-digest"
    },
    {
      "role": "application-sbom",
      "format": "CycloneDX JSON",
      "specVersion": "1.6",
      "file": "application-sbom.cdx.json",
      "sha256": "64-hex-character-digest"
    }
  ],
  "image": {
    "immutableReference": "registry.example.invalid/team/release-demo@sha256:...",
    "sbomFile": "image-sbom.cdx.json"
  }
}
~~~

The digest, repository, and run strings above illustrate format only, not real data. Never use sample values in production metadata. If the deliverable is not a container image, omit the `image` object.

Metadata can also record builder, runner, `startedAt`, `finishedAt`, workflow, `dependencyLockfileHash`, `buildArguments` (non-secret only), and `testSummary`. Keep the schema small and versioned, and never dump all environment variables into JSON.

### 9.2. Generating Metadata in Bash with jq

Example for GitHub-hosted Ubuntu runners and Maven. `jq` guarantees valid JSON escaping without fragile manual string concatenation:

~~~bash
set -eo pipefail

ARTIFACT=dist/release-evidence/release-demo.jar
SBOM=dist/release-evidence/application-sbom.cdx.json

ARTIFACT_SHA=$(sha256sum "$ARTIFACT" | awk '{print $1}')
SBOM_SHA=$(sha256sum "$SBOM" | awk '{print $1}')
SOURCE_COMMIT=$(git rev-parse HEAD)
SOURCE_REF=$GITHUB_REF
BUILD_ID=$GITHUB_RUN_ID
BUILD_URL=$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID
JAVA_VERSION=$(java -version 2>&1 | head -n 1)
MAVEN_VERSION=$(./mvnw -version | head -n 1)

if [ -z "$BUILD_ID" ]; then BUILD_ID=local; fi
if [ -z "$SOURCE_REF" ]; then SOURCE_REF=local; fi

jq -n \
  --arg repository "$GITHUB_REPOSITORY" \
  --arg commit "$SOURCE_COMMIT" \
  --arg ref "$SOURCE_REF" \
  --arg buildId "$BUILD_ID" \
  --arg buildUrl "$BUILD_URL" \
  --arg javaVersion "$JAVA_VERSION" \
  --arg mavenVersion "$MAVEN_VERSION" \
  --arg artifactSha "$ARTIFACT_SHA" \
  --arg sbomSha "$SBOM_SHA" \
  '{
    schemaVersion: 1,
    source: {
      repository: $repository,
      commit: $commit,
      ref: $ref
    },
    build: {
      id: $buildId,
      url: $buildUrl,
      tool: "Maven",
      toolVersion: $mavenVersion,
      javaVersion: $javaVersion,
      springBootVersion: "3.3.13"
    },
    artifacts: [
      {
        role: "application",
        file: "release-demo.jar",
        sha256: $artifactSha
      },
      {
        role: "application-sbom",
        format: "CycloneDX JSON",
        specVersion: "1.6",
        file: "application-sbom.cdx.json",
        sha256: $sbomSha
      }
    ]
  }' > dist/release-evidence/build-metadata.json

(
  cd dist/release-evidence
  sha256sum release-demo.jar application-sbom.cdx.json build-metadata.json > SHA256SUMS
  sha256sum --check SHA256SUMS
)
~~~

The snippet assumes Maven/CI files exist and GitHub Actions environment variables are set. On other CI platforms, substitute the platform's equivalent repository, ref, and run URL variables. For Gradle, replace `MAVEN_VERSION` with `./gradlew --version` output and adjust artifact/SBOM paths to match task outputs.

**Never pass tokens or secrets to `jq --arg` just to populate metadata.** Metadata must include only what is needed to trace the artifact.

### 9.3. Internal and External Metadata Must Agree

If the JAR includes `META-INF/build-info.properties`, verify its group, artifact, and version match `build-metadata.json`. The Git commit may live solely in external metadata. If embedding the commit inside `build-info`, embed only the non-sensitive commit SHA; consider reproducibility impact and avoid embedding internal branch names unnecessarily.

If external metadata states the JAR is version `1.0.0` while archive `build-info` says `0.9.0-SNAPSHOT`, **the pipeline must fail** rather than uploading contradictory evidence.

## 10. Attaching Image Digests and Image SBOMs to Evidence

When CI builds an OCI image, capture the digest **after pushing the image**. With Docker Buildx, you can request a metadata file:

~~~bash
IMAGE_TAG=registry.example.invalid/team/release-demo:1.0.0

docker buildx build \
  --push \
  --tag "$IMAGE_TAG" \
  --metadata-file dist/release-evidence/buildx-metadata.json \
  .

IMAGE_DIGEST=$(jq -r '."containerimage.digest"' dist/release-evidence/buildx-metadata.json)
IMAGE_REF_DIGEST=$IMAGE_TAG@$IMAGE_DIGEST
printf '%s\n' "$IMAGE_REF_DIGEST" > dist/release-evidence/image-reference.txt
~~~

`containerimage.digest` is the manifest/build output digest reported by Buildx. Verify the metadata file has a valid value starting with `sha256:` before proceeding. When using Spring Boot `build-image`/`bootBuildImage` or another CI builder, read the digest from its output or registry rather than assuming Buildx metadata exists.

Generate an SBOM for that exact image digest:

~~~bash
syft "$IMAGE_REF_DIGEST" \
  -o cyclonedx-json=dist/release-evidence/image-sbom.cdx.json
~~~

Then compute the checksum for the image SBOM and update `build-metadata.json` with `image.immutableReference`, `image.digest`, and `image.sbomFile`. **Regenerate `SHA256SUMS` after the final update:**

~~~bash
(
  cd dist/release-evidence
  sha256sum release-demo.jar application-sbom.cdx.json \
    image-sbom.cdx.json build-metadata.json image-reference.txt > SHA256SUMS
  sha256sum --check SHA256SUMS
)
~~~

`buildx-metadata.json` can be kept as raw build output for auditing, after inspecting its contents prior to upload. Never allow secrets, credentials, or full builder environments into metadata files.

## 11. Signing Checksums and Verifying Signatures

### 11.1. Why Sign the Manifest?

SHA-256 detects changes relative to the manifest. A signature lets recipients verify **the manifest was created by a trusted identity**. With keyless signing, CI obtains a short-lived identity via OIDC, avoiding committing private signing keys to the repository.

Sign the checksum manifest with Cosign/Sigstore:

~~~bash
cosign sign-blob --yes \
  --bundle dist/release-evidence/SHA256SUMS.sigstore.json \
  dist/release-evidence/SHA256SUMS
~~~

The bundle holds signature, certificate, and transparency-log evidence per the Sigstore workflow. Store the bundle alongside `SHA256SUMS`; never list the bundle inside the signed checksum manifest itself (avoiding circular dependencies). If using KMS/key-managed signing, follow your organization's key custody and rotation policies.

### 11.2. Verify Before Using the Artifact

Recipients must obtain **expected signer identity** and OIDC issuer from a trusted policy, never from the file under verification:

~~~bash
cosign verify-blob dist/release-evidence/SHA256SUMS \
  --bundle dist/release-evidence/SHA256SUMS.sigstore.json \
  --certificate-identity "$EXPECTED_SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$EXPECTED_OIDC_ISSUER"

(
  cd dist/release-evidence
  sha256sum --check SHA256SUMS
)
~~~

A passing signature check only confirms the signature, identity, and bundle match the supplied trust options. Consumers must still verify that the signer is authorized to release for that project, repository, and branch. Only then verify each file against the manifest.

### 11.3. Signing Container Images by Digest

When the deliverable is an OCI image, sign the immutable reference:

~~~bash
cosign sign --yes "$IMAGE_REF_DIGEST"
~~~

Verify against an approved identity and issuer:

~~~bash
cosign verify "$IMAGE_REF_DIGEST" \
  --certificate-identity "$EXPECTED_SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$EXPECTED_OIDC_ISSUER"
~~~

Never sign a mutable tag and treat the tag as a fixed identity; sign the digest to bind the signature to exact image contents. For SBOMs and provenance, follow your attestation policy; Cosign supports image-attached attestations. An image signature **does not automatically validate an SBOM**; inspect the predicate and subject digest referenced by the attestation.

## 12. Build Provenance and SLSA

A strong release evidence bundle can contain `build-metadata.json` (pipeline-generated, human-readable metadata), `SHA256SUMS` (checksums of evidence files), `SHA256SUMS.sigstore.json` (manifest signature), `provenance.intoto.jsonl` (provenance/attestation from a trusted build platform), and SBOMs (dependency/image inventories).

SLSA provenance typically describes:

- **Subject:** output artifact identified by cryptographic digest.
- **Build definition/type:** build process executed.
- **External parameters:** caller-supplied inputs and parameters.
- **Resolved dependencies:** source commit and resolved dependencies/build inputs known to the platform.
- **Builder identity:** build platform executing the build and emitting provenance.
- **Run details:** invocation ID, timestamps, and build run metadata.

**Never write an arbitrary JSON file and label it SLSA L2/L3.** Build levels depend on trust boundaries, provenance generation/integrity guarantees, and build platform isolation. Enable native provenance/attestation generation from your organization's trusted CI platform, and verify it binds to **the exact digest**.

### 12.1. SBOM and Provenance Are Related Yet Do Not Replace Each Other

- SBOM answers: "which components are declared/detected inside this product?"
- Provenance answers: "which builder produced this artifact, from which inputs, via which process?"
- Checksum answers: "do the current bytes match this digest?"
- Signature answers: "did a trusted identity sign this digest or manifest?"

An SBOM can be generated post-build by a scanner; provenance must reflect the real build process and be authenticated by the build platform. A signature does not prove SBOM accuracy if the scanner or attestation process is untrustworthy.

## 13. GitHub Actions: Uploading the Evidence Bundle in CI Results

The example below illustrates a Maven build uploading evidence with retention. It assumes earlier steps produced the JAR, `target/bom.json`, `build-metadata.json`, `SHA256SUMS`, and signature bundle if signed.

~~~yaml
name: Spring Boot release evidence

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: read
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Build, test and generate SBOM
        run: ./mvnw --batch-mode clean verify

      - name: Verify expected outputs
        run: |
          test -s target/release-demo.jar
          test -s target/bom.json
          test -s target/bom.xml
          jq -e '.bomFormat == "CycloneDX" and .specVersion == "1.6"' target/bom.json

      - name: Assemble release evidence
        run: |
          mkdir -p dist/release-evidence
          cp target/release-demo.jar dist/release-evidence/
          cp target/bom.json dist/release-evidence/application-sbom.cdx.json
          # Generate build-metadata.json and SHA256SUMS per Section 9.

      - name: Upload evidence
        uses: actions/upload-artifact@v7
        with:
          name: spring-boot-release-evidence-${{ github.run_id }}
          path: |
            dist/release-evidence/
          if-no-files-found: error
          retention-days: 30
~~~

This is a **workflow fragment** to integrate into a real pipeline; the `Assemble release evidence` step must run the full metadata/checksum script, and if required by policy, sign the manifest/provenance before upload. Never leave placeholder comments in a live release pipeline.

GitHub Actions `upload-artifact` supports artifact name, paths, `if-no-files-found`, and `retention-days`. Actual retention is bounded by repository, organization, and enterprise limits. On GitHub Enterprise Server, verify action version compatibility with your GHES release; never assume every latest version supports GHES.

### 13.1. Retaining Artifacts per Run and Release

- Use unique names incorporating run ID/version/commit to avoid overwriting outputs from other builds.
- `if-no-files-found: error` ensures the pipeline fails if the JAR or SBOM is missing.
- Set retention per policy; 30 days in the example is not a universal rule.
- Avoid setting `include-hidden-files: true` unless verified necessary, as hidden files can include `.env` or settings files.
- For long-lived releases, publish evidence to an artifact repository or release storage with durable retention and access controls; CI run artifacts eventually expire.
- Keep the JAR, SBOM, metadata, checksums, signatures, and provenance within the same release namespace or linked by digest.

### 13.2. GitLab CI Equivalent

GitLab can preserve the same bundle using `artifacts`:

~~~yaml
build:
  stage: build
  script:
    - ./mvnw --batch-mode clean verify
    - test -s target/release-demo.jar
    - test -s target/bom.json
  artifacts:
    when: always
    name: "spring-boot-evidence-$CI_PIPELINE_ID"
    paths:
      - target/release-demo.jar
      - target/bom.json
      - dist/release-evidence/
    expire_in: 30 days
~~~

This is an illustrative configuration; generate metadata, checksums, and signatures before artifact upload and integrate secrets/OIDC per your GitLab instance. `when: always` helps preserve logs/reports on failure, yet failed QA evidence must **never** be treated as a releasable build. Separate diagnostic artifacts from release artifacts when pipelines fail.

## 14. Validating Evidence Before Upload

### 14.1. Artifact Exists and Has the Right Type

Maven:

~~~bash
test -s target/release-demo.jar
file target/release-demo.jar
jar tf target/release-demo.jar
~~~

Gradle:

~~~bash
test -s build/libs/release-demo.jar
file build/libs/release-demo.jar
jar tf build/libs/release-demo.jar
~~~

Verify the executable JAR genuinely contains `BOOT-INF/classes`, `BOOT-INF/lib`, and the manifest/Boot loader. If the build emits `*-plain.jar`, do not pick the plain archive by mistake. For WARs, verify the `WEB-INF/` layout.

### 14.2. SBOM Parsing and Scope

- JSON/XML parses cleanly.
- `bomFormat` is `CycloneDX`, and `specVersion` matches the expected version.
- `metadata.component` matches project, artifact, and version.
- Component count and dependency graph match dependency reports.
- Test-only dependencies do not leak into runtime SBOMs unless required by policy.
- Multi-module aggregates include only projects actually contributing to the release.
- No secrets appear inside component properties or external references.
- Tool/plugin version that produced the SBOM is recorded.

### 14.3. Hashes and File Mapping

- Filenames in `SHA256SUMS` point to actual files.
- Hashes are computed after JAR and SBOM generation finishes.
- `sha256sum --check` passes inside the exact evidence directory being uploaded.
- If metadata records digests, they match the digests in the manifest.
- If an image exists, the image reference uses a digest, not merely a tag.
- If signatures exist, they verify against the identity and issuer in your trust policy.

### 14.4. No Secrets Leaked in Evidence

Never upload `.m2/settings.xml`, `gradle.properties` containing credentials, `.env`, keystores, private keys, tokens, Docker auth configs, or the full workspace into the evidence bundle. SBOMs and metadata can expose internal dependency names, package coordinates, and repository/source URLs; enforce appropriate access controls.

## 15. Verifying and Reusing Evidence in Downstream Pipelines

A deployment job or release consumer can execute:

~~~bash
# 1. Verify the manifest signature against a trust-policy-allowed identity.
cosign verify-blob dist/release-evidence/SHA256SUMS \
  --bundle dist/release-evidence/SHA256SUMS.sigstore.json \
  --certificate-identity "$EXPECTED_SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$EXPECTED_OIDC_ISSUER"

# 2. Verify bytes of every declared file.
(
  cd dist/release-evidence
  sha256sum --check SHA256SUMS
)

# 3. Validate SBOM JSON and metadata.
jq -e '.bomFormat == "CycloneDX"' \
  dist/release-evidence/application-sbom.cdx.json
jq -e '.schemaVersion == 1 and .source.commit != ""' \
  dist/release-evidence/build-metadata.json
~~~

If the manifest is not signed, omit the signature step while recognizing that checksums alone do not authenticate origin. Production release policies should require signatures/attestations and allowlist authorized signer/builder identities.

Downstream teams can feed the SBOM into CVE scanners with up-to-date vulnerability databases, check dependencies against denylists and license policies, locate affected artifacts when new CVEs emerge, verify approved dependency versions, and archive inventories for audits and compliance.

**Scanner results must also be bound to the exact SBOM/artifact digest.** Record the scanner name/version, database timestamp, policy ID, and scan timestamp; never attach a scan from another commit to the current release.

## 16. Common Pitfalls

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| `target/bom.json` does not exist | Plugin execution skipped, wrong goal/phase, or build failed before verify | Check CycloneDX plugin, execution phase, and logs; fail pipeline if output is required |
| SBOM lists only direct dependencies | Wrong resolution/configuration scope or aggregate/module selection | Check plugin config, resolved dependency graph, and direct/aggregate goal |
| SBOM includes test libraries in runtime list | Plugin scans test configuration/scope | Target `runtimeClasspath` or `includeTestScope=false` matching artifact boundary |
| Aggregate SBOM includes non-released projects | Scanned entire reactor/monorepo instead of component boundary | Use Direct SBOM or restrict projects included in the release aggregate |
| SBOM omits OS/JRE packages | Using project dependency SBOM instead of image SBOM | Scan the image digest with an image-aware tool like Syft |
| Checksum changes after build | JAR/SBOM edited, repackaged after hashing, `build-info` time, or wrong path | Hash after the final step; compare artifact identity and build inputs |
| `sha256sum --check` prints `FAILED` | File altered, wrong download, wrong manifest path, or corrupted archive | Halt publish/deploy; re-download from trusted source and investigate |
| Checksum passes yet artifact is untrusted | Both manifest and file could be replaced together | Verify signatures/attestations and signer identity; checksums alone are insufficient |
| Metadata commit differs from artifact | Dirty build workspace or checkout/ref shifted mid-pipeline | Check out fixed commit, record `git rev-parse HEAD` in same job, avoid using branch name as commit identity |
| Metadata JSON is invalid | Manual string concatenation broke escaping or newlines | Use `jq` or a JSON serializer and parse-check before upload |
| `build-info` time changes JAR on every build | Timestamp embedded in archive | Exclude `time` if reproducibility is required or document build-time policy |
| Image SBOM differs from deployed image | Scanned mutable tag or local image differing from pushed digest | Scan immutable `image@sha256:...` and record digest in metadata |
| CI upload misses SBOM | Wrong glob/path or upload step runs before generation | Use explicit paths and `if-no-files-found: error` |
| CI artifact expires before audit | Retention shorter than release/compliance requirement | Publish evidence to a long-term artifact repository with retention/access policies |
| Cosign verify fails | Signer identity/issuer mismatch, missing bundle, or wrong OIDC trust policy | Check expected identity/issuer and sign step; never drop verification to force green |
| SBOM signed yet unbound to JAR | Attestation fails to bind subject digest or SBOM file was swapped | Attest exact artifact digest, hash SBOM, and verify subject/predicate |
| Self-written JSON labeled as SLSA level | Confused metadata with builder-generated provenance | Use native trusted build platform provenance; never self-assert levels |
| Evidence bundle contains `.env` or credentials | Uploaded entire workspace or hidden files | Upload only allowlisted evidence paths; secret-scan and inspect file list before upload |
| Checksum manifest omits final metadata | Metadata modified after generating `SHA256SUMS` | Write metadata first, then manifest; regenerate manifest and signature on metadata edits |
| Manifest hashes itself | Attempted to include `SHA256SUMS` in its own list | Exclude the manifest from itself; sign the manifest file separately |

## 17. Reproducibility, Retention, and Evidence Security

### 17.1. Build Reproducibility

Checksums show whether bytes match; reproducible builds ensure identical source/inputs produce identical outputs. To improve repeatability:

- Pin JDK/toolchain, Maven/Gradle Wrapper, and plugin versions.
- Lock dependency versions and verify dependency integrity.
- Record builder/run image digests when using CNB or container builds.
- Enable reproducible archive timestamps and ordering where supported by plugins.
- Exclude build timestamps from embedded `build-info` when prioritizing deterministic outputs.
- Record compiler flags, profiles, and non-secret build parameters.
- Avoid dynamic dependency versions in releases requiring reproducibility.

Never claim reproducibility just because two files share a version string; rebuild from identical source and inputs in a controlled environment and compare digests.

### 17.2. Retention and Access Control

Evidence often reveals dependency inventories, internal component names, source refs, build URLs, and image references. Therefore:

- Enforce access controls on CI artifacts and release storage.
- Set retention according to audit, compliance, and release lifecycles.
- Ensure evidence contains zero credentials or private keys.
- Retain signatures and provenance at least as long as the artifacts they verify.
- Maintain mappings linking artifact version, digest, SBOM serial number, build run, and deployment.
- Follow policy when pruning expired artifacts; never delete evidence still needed for open incidents or audits.

### 17.3. SBOMs Do Not Replace Vulnerability Scans

An SBOM tells scanners which components to evaluate. However, CVE status evolves over time; the same SBOM can yield new findings as vulnerability databases update. Record the scan timestamp, scanner/database version, and policy so auditors know when the result was produced.

### 17.4. Never Let Metadata Leak Secrets

Exclude full `env`/system properties, `mvn -X`, `gradle --debug`, registry access tokens, Maven passwords, Git deploy tokens, cloud credentials, unnecessary absolute workspace paths, and raw image build logs containing sensitive command args.

Metadata should capture the commit SHA, access-controlled build run URL, tool versions, artifact digests, and builder identity. You do not need to dump every environment variable to reproduce a build.

## 18. Practice Exercises and Acceptance Criteria

### Exercise A — Maven Application SBOM

1. Create a Java 17 Spring Boot Maven project with artifactId `release-demo`, version `1.0.0`, and executable JAR at `target/release-demo.jar`.
2. Add CycloneDX Maven Plugin 2.9.1 with `makeBom`, schema 1.6, and appropriate runtime scope.
3. Run `./mvnw clean verify`.
4. Confirm the JAR, `target/bom.json`, and `target/bom.xml` exist.
5. Check JSON parsing/schema declaration and compare dependencies against `./mvnw dependency:tree`.
6. For multi-module builds, generate an aggregate SBOM only if it accurately describes the released deliverable.

### Exercise B — Gradle Application SBOM

1. Create the same application using a Gradle Wrapper compatible with CycloneDX plugin 3.4.0 (Gradle 8.4+).
2. Configure `cyclonedxDirectBom` for `runtimeClasspath` and exclude test configs.
3. Run `./gradlew clean test bootBuildInfo bootJar cyclonedxDirectBom`.
4. Confirm `build/libs/release-demo.jar` and `build/reports/cyclonedx-direct/bom.json`.
5. For multi-project builds, compare each module's Direct SBOM against the product's Aggregate SBOM.

### Exercise C — Checksums and Verification

1. Copy the JAR and SBOM into `dist/release-evidence`.
2. Generate `SHA256SUMS` using SHA-256.
3. Run `sha256sum --check`.
4. Make a test copy and flip one byte with a test utility; verify checking fails. Do this strictly on a copy, never the original release artifact.
5. Sign the manifest keyless with Cosign if CI supports OIDC and policy allows it.
6. Verify the signature with the expected signer identity/issuer, then verify hashes.

### Exercise D — Metadata and Image SBOM

1. Create `build-metadata.json` containing commit, ref, build ID/URL, Java/Maven/Gradle versions, artifact path/digest, and SBOM path/digest.
2. If building a container, push the image and capture its real manifest digest.
3. Run Syft against `image@sha256:...` to produce `image-sbom.cdx.json`.
4. Update metadata with the immutable image reference and image SBOM digest.
5. Regenerate `SHA256SUMS` after all final updates.
6. Verify metadata has no tokens/passwords and digests point to the exact deliverables.

### Exercise E — CI Upload and Downstream Verification

1. Create a CI job running tests, packaging, and SBOM generation before uploading.
2. Check that every required file exists; fail the job if any file is missing.
3. Upload `release-evidence/` via GitHub Actions artifacts or equivalent, setting appropriate retention and access controls.
4. Download the artifact in a downstream job, verify its signature, and run `sha256sum --check`.
5. Verify metadata commit/run match the source build; confirm the SBOM matches the expected schema and artifact.
6. If provenance is used, verify the attestation against an allowlist of builder/signer identities.

### Completion Checklist

- [ ] Understand how checksums, SBOMs, build metadata, and provenance differ.
- [ ] Have an executable JAR/WAR with the exact expected version and filename.
- [ ] Have a CycloneDX JSON/XML SBOM from the Maven or Gradle dependency graph.
- [ ] Selected appropriate scopes/configurations and distinguished Direct from Aggregate SBOMs.
- [ ] Have a dedicated OCI image SBOM when a container image is the deliverable.
- [ ] Have a SHA-256 manifest covering the JAR, SBOM, and metadata.
- [ ] Verify checksums after downloading or transferring artifacts.
- [ ] Understand that checksums do not prove authenticity unless the manifest is signed.
- [ ] Include non-secret `build-info.properties` when displaying build versions in-app.
- [ ] Generate `build-metadata.json` recording source commit, run ID/URL, toolchain, and artifact digests.
- [ ] Identify images by immutable manifest digest.
- [ ] Verify Cosign/Sigstore signatures using expected signer identity and issuer.
- [ ] Obtain SLSA provenance from a trusted build platform rather than self-labeled JSON.
- [ ] Configure CI to upload an explicit file allowlist with `if-no-files-found: error` and retention policies.
- [ ] Never upload settings, `.env`, credentials, private keys, or raw secret logs.
- [ ] Downstream pipelines verify signatures, checksums, metadata, and SBOMs prior to deployment.

**Acceptance criteria:** a single CI run produces the executable JAR, application SBOM, `build-metadata.json`, and `SHA256SUMS`; recipients can download the evidence bundle, verify signatures (when enabled), run checksum checks, and match commit/build IDs. If releasing a container image, include the immutable image digest and an image SBOM scanned from that exact digest. If a registry or attestation platform is unavailable, document what remains unverified; never claim SLSA levels or passing image SBOMs from a project dependency report alone.

## Official References

- [Spring Boot 3.3 — Maven Plugin: Build Info](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-info.html)
- [Spring Boot 3.3 — Gradle Plugin: Integrating with Actuator](https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html)
- [CycloneDX Maven Plugin — Usage and Goals](https://github.com/CycloneDX/cyclonedx-maven-plugin)
- [CycloneDX Gradle Plugin — Configuration and Output](https://github.com/CycloneDX/cyclonedx-gradle-plugin)
- [CycloneDX Specification](https://cyclonedx.org/specification/overview/)
- [SLSA v1.2 — Build Provenance](https://slsa.dev/spec/v1.2/build-provenance)
- [Sigstore — Cosign Quickstart](https://docs.sigstore.dev/quickstart/quickstart-cosign/)
- [Sigstore — Signing Other Types, including SBOMs](https://docs.sigstore.dev/cosign/signing/other_types/)
- [Sigstore — Signing and Verifying Blobs](https://docs.sigstore.dev/cosign/signing/signing_with_blobs/)
- [Syft — Output Formats](https://github.com/anchore/syft/wiki/output-formats)
- [GitHub Actions — upload-artifact](https://github.com/actions/upload-artifact)
- [GitHub Docs — Artifact and Log Retention](https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts)

**Key takeaway:** checksums verify bytes; SBOMs inventory components; metadata traces builds; provenance and signatures authenticate origins per trust policy. Bind everything to **the exact artifact digest**, generate the manifest after the final build step, upload one cohesive release evidence bundle, and require downstream pipelines to verify before deploying.