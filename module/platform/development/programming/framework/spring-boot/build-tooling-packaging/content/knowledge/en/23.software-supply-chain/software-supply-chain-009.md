# Recording Build Provenance Evidence and Linking It to Released Artifacts

## 1. Why Does a JAR File Need Provenance Evidence?

A development team may build a Spring Boot application successfully, upload the JAR to a release page, and deploy it to production. Weeks later, operations receives a file with the same name and version from another source. They need to answer:

- Which repository and commit produced this file?
- Which workflow, builder, and toolchain created it?
- Which dependencies and inputs were used?
- Who or what system attested to that information?
- Is the downloaded file the exact artifact that was tested and released?
- Is the image running in Kubernetes the exact image approved by the release team?

Merely writing a filename, version, or Git commit in release notes is not enough. Filenames and tags can be replaced; someone can alter metadata or upload a different binary under the same name.

A stronger approach is generating a **build provenance attestation**: a structured statement describing how an artifact was built, bound to the **cryptographic digest of the artifact itself**, and signed by a verifiable builder/workflow identity. On release, you preserve the link among the source commit, CI run, attestation, and released file/image.

This lesson belongs to the **Supply Chain** topic. We will work with SLSA provenance, in-toto Statements, DSSE, OCI digests, CycloneDX SBOMs, GitHub Artifact Attestations, Sigstore/Cosign, and BuildKit. The main example uses Maven + Java 17 + Spring Boot, then extends to container images.

## 2. Distinguishing Four Types of Evidence

These terms frequently appear together yet answer different questions.

| Evidence | Question answered | Key contents |
| --- | --- | --- |
| **Checksum / digest** | Are these the exact recorded bytes? | SHA-256 of JAR, image manifest, or file |
| **Build provenance** | Where was the artifact built, by which builder, via what process? | Source, builder, build type, inputs, invocation, output subject |
| **SBOM** | Which software components does the artifact contain? | Dependencies, versions, package identifiers, hashes, licenses per tool |
| **Signature / attestation envelope** | Who signed the statement and is the signature valid? | Signature, certificate/identity, timestamp/transparency proof |

A SHA-256 sidecar file like **app.jar.sha256** helps detect file modification when the verifier holds a trusted digest. Yet a checksum alone does not tell you who built the file or from which source.

An SBOM describes components; it does not prove the application was built from an approved commit. Provenance describes the build process; it does not automatically enumerate every package inside a runtime image if the build platform did not record those components.

A signature proves a specific identity signed the specified payload. It does not prove every claim inside is truthful. You must verify the **signature, identity, subject digest, predicate type, and build policy**.

## 3. Chain of Links from Source to Release

The goal is an end-to-end traceable chain:

~~~text
Git repository + protected tag/commit
                |
                v
CI workflow + builder identity
                |
                v
Build inputs / toolchain / dependencies
                |
                v
Maven package + tests + SBOM
                |
                v
Artifact bytes -> SHA-256 digest
                |
                v
Signed in-toto / SLSA provenance attestation
                |
                v
Release asset or OCI registry image
                |
                v
Release record links artifact digest + attestation
                |
                v
Consumer verifies before install/deploy
~~~

Two identities must be distinguished:

- **Source identity**: the repository, branch/tag, and commit that supplied the source.
- **Builder identity**: the workflow/service that actually ran the build and signed the provenance.

One commit can be built by multiple workflows. One workflow can run on different commits. Therefore, do not store only a Git SHA; link source identity with builder/workflow identity and output digest in the same provenance.

### 3.1. Values to Link

| Element | Example | Purpose |
| --- | --- | --- |
| Repository | github.com/acme/catalog-service | Where source is stored |
| Source ref | refs/tags/v1.0.0 | Release label |
| Source commit | 40-character Git SHA | Identifies the exact source tree |
| Workflow | .github/workflows/release.yml | Identifies the build process |
| Workflow run | run ID + attempt | Identifies a single execution |
| Builder | GitHub-hosted runner / trusted builder | Identifies the build platform |
| Toolchain | Java 17, Maven Wrapper, plugin versions | Explains the build environment |
| Dependencies | groupId:artifactId:version + digest if available | Records inputs |
| Artifact subject | target/app.jar + sha256 digest | Binds provenance to the actual file |
| Release reference | release URL / registry digest | Where consumers retrieve the artifact |

**A source commit SHA is not an artifact digest.** A commit hash identifies a Git object; a JAR's SHA-256 identifies the bytes of the released file. Both values play distinct roles.

## 4. Digests: Filename-Independent Identifiers

### 4.1. Why Filenames and Tags Are Not Enough

Two files can share the same name:

~~~text
catalog-service-1.0.0.jar
~~~

yet contain completely different bytes. Likewise, a Docker tag such as:

~~~text
registry.example.com/acme/catalog-service:1.0.0
~~~

is a mutable reference that can be updated to point to another image. Tags are useful for humans, but they are not immutable content identifiers.

A digest uses a cryptographic hash to identify content. Example:

~~~text
sha256:4a1f... (64 hex characters)
~~~

In real usage, all 64 hex characters must be present; the abbreviation here only illustrates format.

### 4.2. Generating SHA-256 for a JAR

Linux/macOS:

~~~bash
sha256sum target/catalog-service-1.0.0.jar
~~~

Save the checksum:

~~~bash
sha256sum target/catalog-service-1.0.0.jar > target/catalog-service-1.0.0.jar.sha256
~~~

Verify the file:

~~~bash
sha256sum -c target/catalog-service-1.0.0.jar.sha256
~~~

If the file matches, output typically looks like:

~~~text
target/catalog-service-1.0.0.jar: OK
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\target\catalog-service-1.0.0.jar -Algorithm SHA256
~~~

**Note:** checksum verification is only meaningful when the checksum file comes from a trusted channel. If an attacker replaces both the JAR and the .sha256 file, they will still match. Signed provenance and identity verification validate the origin of the digest.

### 4.3. Container Image Digests

For OCI images, a digest typically identifies a manifest or image index. Example:

~~~text
ghcr.io/acme/catalog-service@sha256:012345...
~~~

Use **image@sha256:digest** whenever you need to reference exact verified content. Tags can still help operators discover releases easily, but deployment policy should pin to approved digests.

For multi-platform images, one digest can identify an **image index** containing platform manifests; the linux/amd64 manifest digest differs from the linux/arm64 manifest digest. During investigations, check whether the attestation subject binds to the index or to a specific platform manifest.

Per the OCI Image Specification, a descriptor contains a media type, digest, and byte size; consumers should verify downloaded content matches the digest before processing. Source: https://github.com/opencontainers/image-spec/blob/main/descriptor.md

## 5. What Is Provenance?

**Build provenance** is structured metadata describing how an artifact was built, with which inputs, and by which builder. It can answer:

- Which source repository/commit was used?
- Which build type or pipeline ran?
- Which external parameters influenced the build?
- Which dependencies/materials were resolved?
- What is the builder identity?
- When did the build invocation start and finish?
- Which output artifacts were produced, and with what digests?

SLSA defines a build provenance predicate within the in-toto Attestation Framework. Currently used predicate URI:

~~~text
https://slsa.dev/provenance/v1
~~~

**Never hand-craft a JSON file and call it trustworthy provenance.** What matters is that the data is generated by a builder with a clear trust boundary, signed/authenticated, and independently verifiable.

### 5.1. Key Fields in SLSA Provenance v1

A SLSA provenance predicate has two main sections:

| Section | Field | Meaning |
| --- | --- | --- |
| Build definition | buildType | Template/process of the build that ran |
| Build definition | externalParameters | Inputs controlled by an external caller/tenant |
| Build definition | internalParameters | Parameters managed by the build platform |
| Build definition | resolvedDependencies | Resolved dependencies/materials |
| Run details | builder.id | Builder identifier |
| Run details | metadata.invocationId | Build run identifier |
| Run details | metadata.startedOn / finishedOn | Build timestamps |
| Run details | byproducts | Secondary outputs if any |
| Statement | subject | Output artifact and digest |

SLSA requires external parameters to be complete at Build Level 3; this matters because if an unrecorded external input exists, verifiers cannot faithfully reconstruct the build definition.

### 5.2. Abbreviated Statement Example

The JSON below illustrates structure only; values are hypothetical and **not a signed attestation**:

~~~json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "catalog-service-1.0.0.jar",
      "digest": {
        "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
      }
    }
  ],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://example.com/buildtypes/maven-release/v1",
      "externalParameters": {
        "repository": "https://github.com/acme/catalog-service",
        "ref": "refs/tags/v1.0.0"
      },
      "resolvedDependencies": [
        {
          "uri": "git+https://github.com/acme/catalog-service",
          "digest": {
            "gitCommit": "0123456789abcdef..."
          }
        }
      ]
    },
    "runDetails": {
      "builder": {
        "id": "https://github.com/acme/catalog-service/actions"
      },
      "metadata": {
        "invocationId": "123456789-1",
        "startedOn": "2026-11-09T02:00:00Z",
        "finishedOn": "2026-11-09T02:03:00Z"
      }
    }
  }
}
~~~

This is a **simplified structural example for learning**. Real provenance must conform to the build platform's schema and semantics; never assign arbitrary builder.id or buildType values and treat claims as verified.

### 5.3. Subject Is the Most Critical Link

Inside a Statement, **subject** identifies the artifact the attestation describes. For a JAR, the subject typically contains the filename and SHA-256. For an image, the subject uses the image name and digest.

If provenance refers to:

~~~text
catalog-service-1.0.0.jar + sha256:AAA...
~~~

while the actual release asset has digest:

~~~text
sha256:BBB...
~~~

then that provenance does not prove the origin of the release file in hand. You must regenerate or retrieve the exact attestation matching digest BBB; never edit the subject in JSON by hand.

## 6. in-toto Statements, Envelopes, and DSSE

The in-toto Attestation Framework separates layers:

1. **Predicate**: claim payload following a specific schema, such as SLSA provenance or CycloneDX.
2. **Statement**: binds a predicate to subject artifacts and states the predicate type.
3. **Envelope**: wrapper format handling authentication/signatures.
4. **Bundle**: packages an attestation together with related verification material.

DSSE (Dead Simple Signing Envelope) is a widely used envelope format for signing payloads in a verifiable way.

Diagram:

~~~text
Artifact bytes
     |
     v
SHA-256 digest
     |
     v
in-toto Statement
  subject + predicateType + predicate
     |
     v
DSSE envelope
     |
     v
Signature + certificate / transparency evidence
     |
     v
Attestation bundle
~~~

**A Statement is not signed by itself.** A bare JSON Statement stored in a repository can be altered. You must verify the envelope/signature, certificate chain or trust root, and transparency evidence per your system.

## 7. How Does an SBOM Differ from Provenance?

A **Software Bill of Materials (SBOM)** is an inventory of software components inside an artifact or build process. It can list:
- Component names, versions, package URLs (purl).
- Suppliers/authors and licenses where collected by tooling.
- Component hashes.
- Dependency relationships.
- Metadata identifying the SBOM document.

SBOMs support inventorying, vulnerability scanning, license reviews, and incident response. Yet an SBOM does not prove source commits or builder identities.

### 7.1. CycloneDX for Maven

CycloneDX Maven Plugin can generate an SBOM for direct and transitive dependencies in a Maven project.

Add the plugin to the POM:

~~~xml
<plugin>
    <groupId>org.cyclonedx</groupId>
    <artifactId>cyclonedx-maven-plugin</artifactId>
    <version>2.9.3</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>makeAggregateBom</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <outputFormat>json</outputFormat>
        <outputName>bom</outputName>
    </configuration>
</plugin>
~~~

With this configuration, output is typically:

~~~text
target/bom.json
~~~

The **makeAggregateBom** goal is useful for multi-module Maven reactors because it aggregates module dependency BOMs. The **makeBom** goal generates a per-module BOM; **makePackageBom** targets packaging such as WAR/EAR per plugin support.

Plugin versions must be managed and updated like any other dependency/plugin. This example uses 2.9.3 for a concrete release version; check compatibility with the CycloneDX schema supported by your SBOM consumers.

### 7.2. A JAR SBOM Is Not Necessarily a Container Image SBOM

CycloneDX Maven plugin describes Maven project dependencies. A container image can also contain:
- Run image/base OS packages.
- JRE and native libraries.
- Files added by buildpacks or Dockerfiles.
- Agent/monitoring binaries.
- Packages outside the Maven dependency graph.

Therefore, when releasing a container image, generate an **image SBOM** using appropriate builders/tooling and bind it to the image digest. Never use a JAR's SBOM to claim you listed every package inside an image.

## 8. Creating an Illustrative Maven Project

The example uses Java 17 and Spring Boot 3.5.16. Specific versions serve this lesson; real projects should select a Spring Boot branch supported by the organization.

### 8.1. Directory Structure

~~~text
provenance-demo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...
└── src/
    ├── main/java/com/example/provenance/
    │   ├── ProvenanceDemoApplication.java
    │   └── BuildController.java
    ├── main/resources/application.properties
    └── test/java/com/example/provenance/
        └── BuildControllerTest.java
~~~

The Maven Wrapper must be generated via Spring Initializr or the Maven Wrapper plugin; a POM alone does not generate wrapper scripts and metadata.

### 8.2. Main Class

File **src/main/java/com/example/provenance/ProvenanceDemoApplication.java**:

~~~java
package com.example.provenance;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProvenanceDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProvenanceDemoApplication.class, args);
    }
}
~~~

### 8.3. Controller

File **src/main/java/com/example/provenance/BuildController.java**:

~~~java
package com.example.provenance;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BuildController {

    @GetMapping("/build")
    public String build() {
        return "provenance-demo-ok";
    }
}
~~~

When the application runs successfully, GET /build returns the exact body:

~~~text
provenance-demo-ok
~~~

### 8.4. application.properties

~~~properties
spring.application.name=provenance-demo
server.port=8080
~~~

### 8.5. Test

File **src/test/java/com/example/provenance/BuildControllerTest.java**:

~~~java
package com.example.provenance;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BuildControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void buildEndpointReturnsExpectedBody() throws Exception {
        mvc.perform(get("/build"))
                .andExpect(status().isOk())
                .andExpect(content().string("provenance-demo-ok"));
    }
}
~~~

The test verifies source behavior before release. It does not replace verifying provenance, digests, or container images.

### 8.6. Complete POM

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>provenance-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
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
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals>
                            <goal>makeAggregateBom</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <outputFormat>json</outputFormat>
                    <outputName>bom</outputName>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**project.build.outputTimestamp** helps supporting plugins create archives with stable timestamps; it does not by itself guarantee all build metadata is deterministic. The value in the POM is an illustrative marker; release policies may derive it from finalized commit/tag metadata.

### 8.7. Build and Inspect Outputs

Linux/macOS:

~~~bash
./mvnw --version
./mvnw -B -ntp clean verify
~~~

With this Maven project, expected outputs are:

~~~text
target/provenance-demo-1.0.0.jar
target/bom.json
~~~

Verify files:

~~~bash
test -f target/provenance-demo-1.0.0.jar
test -f target/bom.json
sha256sum target/provenance-demo-1.0.0.jar target/bom.json
git rev-parse HEAD
git status --short
~~~

On Windows use **mvnw.cmd** and **Get-FileHash**. If the POM changes finalName/classifier or plugin config, actual filenames may differ; use the exact released artifact.

## 9. Generating Provenance Attestations in GitHub Actions

GitHub Artifact Attestations uses OIDC identity and Sigstore to produce signed attestations. For binaries, the **actions/attest** action automatically computes the digest from **subject-path** and generates a SLSA build provenance attestation.

The workflow must grant only the minimum required permissions:
- **id-token: write** so the action can obtain an OIDC token and request a signing certificate.
- **attestations: write** to persist the attestation.
- **contents: read** to check out source.
- **artifact-metadata: write** if the workflow needs to create linked artifact storage records.
- **contents: write** only when the workflow creates/uploads a GitHub Release.
- **packages: write** when publishing images to GHCR.

### 9.1. Workflow to Build and Attest a JAR

Create **.github/workflows/release.yml**:

~~~yaml
name: Build and attest release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest

    permissions:
      contents: write
      id-token: write
      attestations: write
      artifact-metadata: write

    steps:
      - name: Checkout source
        uses: actions/checkout@v6

      - name: Set up Java
        uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: "17"
          cache: maven

      - name: Build, test and generate SBOM
        run: ./mvnw -B -ntp clean verify

      - name: Generate build provenance
        id: provenance
        uses: actions/attest@v4
        with:
          subject-path: target/provenance-demo-1.0.0.jar

      - name: Generate SBOM attestation
        id: sbom
        uses: actions/attest@v4
        with:
          subject-path: target/provenance-demo-1.0.0.jar
          sbom-path: target/bom.json

      - name: Create checksum
        run: sha256sum target/provenance-demo-1.0.0.jar > target/provenance-demo-1.0.0.jar.sha256

      - name: Create release evidence index
        env:
          PROVENANCE_URL: ${{ steps.provenance.outputs.attestation-url }}
          SBOM_ATTESTATION_URL: ${{ steps.sbom.outputs.attestation-url }}
          SOURCE_COMMIT: ${{ github.sha }}
          SOURCE_REF: ${{ github.ref }}
          WORKFLOW_RUN: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        run: |
          python - <<'PY'
          import hashlib
          import json
          import os
          from pathlib import Path

          artifact = Path("target/provenance-demo-1.0.0.jar")
          digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

          record = {
              "artifact": artifact.name,
              "sha256": digest,
              "sourceCommit": os.environ["SOURCE_COMMIT"],
              "sourceRef": os.environ["SOURCE_REF"],
              "workflowRun": os.environ["WORKFLOW_RUN"],
              "provenanceAttestation": os.environ["PROVENANCE_URL"],
              "sbomAttestation": os.environ["SBOM_ATTESTATION_URL"]
          }

          Path("target/release-evidence.json").write_text(
              json.dumps(record, indent=2) + "\n",
              encoding="utf-8"
          )
          PY

      - name: Publish release assets
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          if gh release view "$GITHUB_REF_NAME" >/dev/null 2>&1; then
            gh release upload "$GITHUB_REF_NAME" target/provenance-demo-1.0.0.jar target/provenance-demo-1.0.0.jar.sha256 target/bom.json target/release-evidence.json --clobber
          else
            gh release create "$GITHUB_REF_NAME" target/provenance-demo-1.0.0.jar target/provenance-demo-1.0.0.jar.sha256 target/bom.json target/release-evidence.json --generate-notes
          fi
~~~

This is an illustrative workflow for a tag release. In production:
- Pin GitHub Actions to full commit SHAs or use dependency lockfiles per policy; action tags can change.
- Protect release tags and control who is permitted to create tags.
- Derive artifact versions dynamically from Maven metadata rather than hard-coding if the release workflow handles multiple versions.
- Separate privileged publish jobs from build/test jobs when limiting blast radius.
- Verify repository/plan support for Artifact Attestations. Current documentation notes GitHub Free/Pro/Team supports public repositories, while private/internal repositories require GitHub Enterprise Cloud.

### 9.2. What Gets Signed?

The **Generate build provenance** step hashes the JAR at subject-path and creates an attestation bound to that artifact. The **Generate SBOM attestation** step attaches the CycloneDX document to the same subject JAR.

The two attestations carry different predicates:
- Provenance describes source/build process/builder.
- The SBOM attestation links the BOM to the artifact and enables component verification.

Never rely on the attestation URL alone as an artifact identifier; always store both the **artifact SHA-256** and attestation link. If the JAR is altered after attestation, its digest changes and verification must fail.

### 9.3. Attestation URLs and Bundles

The action can output:
- **attestation-url**: link to the attestation record in GitHub.
- **bundle-path**: path to the Sigstore bundle JSON on the runner.
- **attestation-id**: ID of the record.

You can store the bundle as a release evidence file or CI artifact to support offline verification per policy. If uploaded separately, verify it binds to the right subject digest and preserve the bundle bytes intact. Never edit the bundle JSON after the action generates the signature.

## 10. Verifying JAR Provenance Before Use

Install GitHub CLI and authenticate with an account permitted to read the repository/attestations. Check versions:

~~~bash
gh --version
gh auth status
~~~

Verify the JAR file:

~~~bash
gh attestation verify target/provenance-demo-1.0.0.jar --repo ORG/REPO
~~~

This command verifies an attestation matching the supplied file's digest and the specified repository. For stricter policy enforcement, check the signer workflow and source ref:

~~~bash
gh attestation verify target/provenance-demo-1.0.0.jar --repo ORG/REPO --signer-workflow ORG/REPO/.github/workflows/release.yml --source-ref refs/tags/v1.0.0
~~~

**ORG/REPO** and tags are placeholders; replace them with your real repository/tag. When using reusable workflows, the signer identity is the reusable workflow that signed the attestation, not necessarily the caller workflow; specify the right **signer-workflow** or **signer-repo**.

By default, GitHub CLI checks predicate type **https://slsa.dev/provenance/v1**. When verifying an SBOM attestation, pass **--predicate-type** with the exact predicate URI recorded in the Statement; do not assume every CycloneDX version shares the same versioned URI.

### 10.1. Inspecting Verification Results

~~~bash
gh attestation verify target/provenance-demo-1.0.0.jar --repo ORG/REPO --format json
~~~

JSON output can contain:
- Certificate identity and OIDC issuer.
- Verified timestamps from transparency logs or timestamp authorities.
- Statement subject and digest.
- Predicate type and predicate data.

When building automated policies, distinguish which claims come from certificate/transparency evidence versus predicate content produced by the build workflow. If an attacker controls workflow execution, they can forge certain predicate fields; trusted builders and isolated signer workflows help mitigate that risk.

### 10.2. Verifying Checksums After Download

Consumers download release assets:

~~~bash
sha256sum -c provenance-demo-1.0.0.jar.sha256
~~~

Then verify the attestation of the downloaded file:

~~~bash
gh attestation verify provenance-demo-1.0.0.jar --repo ORG/REPO
~~~

The two checks complement each other. The checksum detects files that differ from the published digest; the attestation verifies that digest carries a provenance claim signed by the expected identity.

## 11. Linking Provenance to Released OCI Images

For container images, the subject must be the **image manifest/index digest**, not the digest of the inner JAR and not a mutable tag.

Process:
1. Build and push the image to the registry.
2. Capture the digest output from the builder.
3. Generate an attestation using the full image name and digest.
4. Publish/record the release tag as a human-friendly label.
5. Deploy using the verified image digest.

### 11.1. GitHub Actions + Buildx + GHCR

Example workflow fragment (to be added to a container release job or separate job):

~~~yaml
permissions:
  contents: read
  id-token: write
  attestations: write
  packages: write
  artifact-metadata: write

steps:
  - name: Log in to GHCR
    uses: docker/login-action@v3
    with:
      registry: ghcr.io
      username: ${{ github.actor }}
      password: ${{ github.token }}

  - name: Build and push image
    id: image
    uses: docker/build-push-action@v6
    with:
      context: .
      push: true
      tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
      provenance: mode=max
      sbom: true

  - name: Generate signed image provenance
    id: image-attestation
    uses: actions/attest@v4
    with:
      subject-name: ghcr.io/${{ github.repository }}
      subject-digest: ${{ steps.image.outputs.digest }}
      push-to-registry: true
~~~

In image attestation:
- **subject-name** is the fully qualified image name without a tag.
- **subject-digest** is the SHA-256 digest returned by Buildx, formatted as sha256:...
- **push-to-registry=true** stores the attestation in the registry; the action can also create linked artifact storage records when the workflow holds appropriate permissions.

BuildKit **provenance=mode=max** and **sbom=true** generate additional build attestations. GitHub **actions/attest** creates a signed attestation under GitHub OIDC identity. These two mechanisms complement each other; they are neither the same signature nor the same trust root.

### 11.2. Verifying Image Attestations

Log in to the registry and verify:

~~~bash
docker login ghcr.io
gh attestation verify oci://ghcr.io/ORG/IMAGE:TAG --repo ORG/REPO
~~~

In deployment policies, resolve and verify the built/published digest, then deploy using:

~~~text
ghcr.io/ORG/IMAGE@sha256:IMAGE_DIGEST
~~~

For multi-platform images, know whether the verified subject digest is the image index or a platform-specific manifest. Never swap the digest back to a tag after verification; the tag may point to a different artifact on a subsequent pull.

## 12. BuildKit Provenance and SBOM

Docker Buildx can generate attestations during build:

~~~bash
docker buildx build --tag ghcr.io/acme/catalog-service:1.0.0 --provenance=mode=max --sbom=true --push .
~~~

Flags:
- **--provenance=mode=max** requests provenance more detailed than minimal.
- **--sbom=true** requests an SBOM attestation.
- **--push** pushes the image and attestations to the registry.

BuildKit generates provenance as in-toto JSON and attaches attestations to the image index/manifest per BuildKit's storage model. **Minimal provenance** may be generated by default; use mode=max when richer build details are needed. Never place secrets in Docker ARG/ENV because build metadata can expose non-public configuration values.

### 12.1. Why Are Attestations Not Visible in Local Docker Images?

The default Docker Engine image store may not persist attestations. Docker documentation notes attestations persist when pushed directly to a registry with the default image store; another option is enabling the containerd image store, which supports attestations.

Therefore:
- When building locally with **--load**, do not assume provenance/SBOM remains in the local image store.
- When consumers need evidence from a registry, build/push directly and inspect registry artifacts.
- When using the containerd image store, verify your Docker Engine version and storage configuration.

### 12.2. Is BuildKit Provenance a Signature?

Do not conflate the two concepts. BuildKit generates build attestation metadata. To verify signer identity and authenticity, a dedicated signature/attestation mechanism such as Sigstore/Cosign or GitHub Artifact Attestations is needed.

In your release policy, explicitly define:
- Provenance source: BuildKit, GitHub Actions, buildpacks, or internal builder.
- Signature/identity source: Sigstore OIDC, KMS key, hardware key, or signing service.
- Attestation storage location: GitHub API, OCI registry referrers, or bundle store.
- Verification rules: subject digest, predicate type, issuer, workflow identity, and builder.

## 13. Cosign/Sigstore for Registry Independence Outside GitHub

If an organization does not use GitHub Artifact Attestations, **Sigstore Cosign** is a common choice for signing images and verifying attestations. Cosign supports both key-based and keyless signing; with keyless signing, OIDC identity is bound to a short-lived certificate and transparency log.

Example verifying an attestation on an image signed with SLSA provenance:

~~~bash
cosign verify-attestation --type slsaprovenance --certificate-identity-regexp '^https://github.com/ORG/REPO/.github/workflows/release.yml@refs/tags/v.*$' --certificate-oidc-issuer https://token.actions.githubusercontent.com ghcr.io/ORG/IMAGE@sha256:IMAGE_DIGEST
~~~

This is a **verification** command. The identity regex must match the real certificate SAN issued by the signing system; never copy placeholders verbatim. With key-based signing, verify against a public key distributed through a trusted channel.

Rego/CUE policies can be used with Cosign to validate predicate contents in addition to the signature. **A valid signature with a policy-violating predicate must still be rejected.**

## 14. Attaching Evidence to GitHub Releases

A release should provide an easily discoverable set of evidence:

~~~text
Release v1.0.0
├── provenance-demo-1.0.0.jar
├── provenance-demo-1.0.0.jar.sha256
├── bom.json
├── release-evidence.json
└── GitHub attestation record / bundle
~~~

Roles:
- JAR: the installable binary.
- SHA-256: checksum sidecar to detect changes.
- bom.json: SBOM for component inspection.
- release-evidence.json: index linking commit, artifact digest, workflow run, provenance URL, and SBOM URL.
- Attestation: signed claim bound to the subject digest.

### 14.1. Example release-evidence.json

~~~json
{
  "release": "v1.0.0",
  "source": {
    "repository": "https://github.com/acme/provenance-demo",
    "ref": "refs/tags/v1.0.0",
    "commit": "0123456789abcdef0123456789abcdef01234567"
  },
  "build": {
    "workflow": ".github/workflows/release.yml",
    "runId": "123456789",
    "builder": "GitHub Actions"
  },
  "artifact": {
    "name": "provenance-demo-1.0.0.jar",
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "releaseAsset": "https://github.com/acme/provenance-demo/releases/download/v1.0.0/provenance-demo-1.0.0.jar"
  },
  "evidence": {
    "provenanceAttestation": "https://github.com/acme/provenance-demo/attestations/123",
    "sbomAttestation": "https://github.com/acme/provenance-demo/attestations/124",
    "sbom": "bom.json"
  }
}
~~~

This is an **index template**, not signed provenance. It helps humans locate evidence; consumers must still cryptographically verify attestations and compare the release asset's digest.

### 14.2. Never Rebuild After Attesting and Upload a Different File

Correct sequence:
1. Build/test.
2. Generate SBOM.
3. Compute digest and generate attestation.
4. Upload **those exact bytes** to the release.
5. Consumer downloads file, recomputes digest, and verifies attestation.

Re-running Maven after attestation and uploading the newly built JAR—even with the same name and version—can change the digest. If a rebuild is necessary, generate new provenance and update the release/evidence under change control.

## 15. Generating Evidence for Spring Boot Images Built with Buildpacks

When using Maven **spring-boot:build-image** or Cloud Native Buildpacks, the image is created by a builder/buildpacks rather than a custom Dockerfile. Provenance must capture:
- Source commit/repository.
- Maven command and plugin version.
- Builder image and buildpack IDs/versions.
- Run image reference/digest.
- Java version/JDK provider.
- Dependency inputs and application artifact digest.
- Final OCI image digest.

Never write generically “built by Maven” if the actual builder was Paketo/CNB. Builder identity and buildpack versions are critical parts of the supply chain.

With Spring Boot buildpacks:
1. Pin builder/run images by version or digest.
2. Retain Maven Wrapper, POM, plugin versions, and dependency lock/management policies.
3. Build images on CI runners with controlled identities.
4. Capture the final registry digest.
5. Create a signed attestation with the image digest as subject.
6. Retain both the application SBOM and image SBOM when required by inventory scope.
7. Verify the attestation before deployment.

If the builder does not natively emit SLSA provenance, CI can use a trusted workflow to generate provenance for the final image. Ensure the subject digest is the **exported image**, not an intermediate JAR or builder cache.

## 16. What Must Be Checked When Verifying Provenance

A verify command returning success is only the first step. Consumers need an explicit **policy**.

### 16.1. Subject

- Does the artifact name match the expected artifact?
- Does the digest match the exact file/image about to be used?
- Is the digest algorithm acceptable (typically SHA-256)?
- Was a tag mistaken for a digest?

### 16.2. Source Identity

- Does the repository belong to the trusted organization/project?
- Is the source commit an approved commit/tag?
- Is the tag protected or signature-verified per release policy?
- Did the workflow run from the right source ref?

### 16.3. Builder Identity

- Does the Builder ID belong to an organization-approved platform?
- Does the workflow path match the release workflow?
- Is the signer repository correct?
- Are the OIDC issuer, certificate chain, and transparency evidence valid?
- Was a trusted reusable workflow used when isolation is required?

### 16.4. Build Inputs

- Do Java, Maven, and Spring Boot Plugin versions match policy?
- Are builder/buildpack/run images pinned?
- Were dependencies resolved from approved repositories?
- Are there unexpected build arguments or environment values?
- Were any untrusted caches or pull-request artifacts used?

### 16.5. Predicate Type and Completeness

- Is the predicate SLSA provenance v1?
- Are the subject digest and buildDefinition present?
- Are external parameters complete per the target level/policy?
- Are resolved dependencies sufficient to explain inputs?
- Is the Builder ID evaluated by the trust platform?

**Never accept provenance simply because the JSON contains repository and commit fields.** Workflows can self-report fields. Verify the signing identity and the builder's level of assurance.

## 17. SLSA Levels: Do Not Claim a Level Just Because You Have a Provenance File

SLSA is a framework for describing and incrementally strengthening supply-chain security. Build provenance is a core component, yet SLSA Build Levels also impose requirements on the build platform, isolation, provenance completeness, and tamper resistance.

Do not claim “SLSA Level 3 compliant” merely because:
- There is a JSON file named provenance.
- You used a GitHub Action to generate attestations.
- You have a Cosign signature.
- You have an SBOM.
- The CI workflow succeeded.

You must accurately assess the builder, trust boundaries, source/config controls, completeness of parameters/dependencies, isolation of the signer from untrusted callers, and consumer verification.

SLSA v1.2 specifies that Build Level 3 requires complete externalParameters, meaning no unrecorded external input can influence the build. That is why workflow and builder isolation matter.

## 18. Protecting Workflows and Builder Identity

A signed provenance attestation can still make false claims if an attacker controlled the workflow/build context. Safeguards:

- Use protected branches/tags and require reviews on release workflows.
- Deny untrusted pull requests access to release credentials or signing permissions.
- Separate build/test jobs from publish/sign jobs where clear trust boundaries are needed.
- Use reusable trusted workflows or managed builders with dedicated policies.
- Pin GitHub Actions to full commit SHAs or dependency lockfiles.
- Restrict GITHUB_TOKEN permissions per job.
- Never put secrets into Docker build args, Maven command-line flags, or environments captured in provenance.
- Avoid mutable builder/action tags on critical releases without change control.
- Restrict permissions to publish images and release assets.
- Monitor changes to workflow files and branch protection rules.

### 18.1. Pull Requests and Forks

Builds for pull requests from forks should run with minimal permissions and no publish/sign rights. When a workflow inspects untrusted code, an attacker may attempt to modify scripts to steal tokens or forge artifacts.

Build releases only from approved refs. When validating pull requests, produce temporary CI artifacts and never sign them with a consumer-trusted release identity.

### 18.2. Self-Hosted Runners

Self-hosted runners must be hardened like build infrastructure. A compromised runner can tamper with source checkouts, build outputs, and signing contexts. Use ephemeral runners, isolate jobs, patch hosts, restrict network access, and never mix trusted and untrusted workloads on the same runner without strong isolation.

## 19. Evidence Storage and Lifecycle

Provenance is only valuable if consumers and auditors can retrieve it when needed.

Define:
- Whether attestations live in the GitHub API, OCI registry, transparency log, or internal evidence store.
- Whether offline bundles are stored alongside the release.
- Whether SBOMs are retained per release and version.
- How long build logs and workflow runs are retained.
- Whether image registry retention deletes artifact referrers/attestations.
- Who is allowed to delete/edit release assets.
- How evidence is replicated across registry regions/accounts.
- Procedures to revoke or flag compromised artifacts.

Do not keep only a URL to a workflow run if runs/logs expire under retention. Persist bundles/attestations in durable storage per policy alongside digests and lookup metadata.

### 19.1. Minimum Release Record

A release record should contain:
- Product/module + version.
- Git repository + commit + tag.
- Artifact filename + SHA-256.
- OCI image name + digest if applicable.
- Builder/workflow identity + run ID.
- Provenance attestation URL/ID/bundle.
- SBOM URL/digest/format/schema version.
- Test/security scan results.
- Release date and approver/automation identity.

This record serves as an index to the evidence; it does not replace signatures or attestations.

## 20. Incident Response: When a Dependency CVE Is Discovered

Suppose a critical vulnerability is discovered in a library used by a Spring Boot service. The security team needs to identify all affected releases.

Procedure:
1. Use SBOMs to find artifacts containing the affected package/version.
2. Use provenance to trace the source commit, build run, and dependency resolution that created each artifact.
3. Locate image digests/releases produced from that artifact.
4. Identify which deployments are currently running affected digests.
5. Build a fix from reviewed source code.
6. Generate new SBOM/provenance, and verify digests and signers.
7. Publish the new image and deploy by the new digest.
8. Retain evidence for both old and new releases for auditing.

Never alter an old release's SBOM to make it look free of the vulnerable package. An SBOM must reflect the actual artifact that was shipped. Generate a new SBOM for the new artifact while keeping clear lineage across versions.

## 21. Verifying Provenance During Kubernetes Deployment

A strong pipeline does not verify only on developer laptops. The deployment admission/policy layer can require:
- Image references use digests.
- A provenance attestation exists.
- Subject digest matches the deployed image.
- Signer workflow/repository matches policy.
- Source ref/commit belongs to an allowed release.
- Builder is on the allowlist.
- SBOM exists and passes vulnerability/license policies.

Example manifest:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      containers:
        - name: app
          image: ghcr.io/acme/catalog-service@sha256:0123456789abcdef...
          ports:
            - containerPort: 8080
~~~

The shortened digest is illustrative only; Kubernetes image references must use valid full digests. An admission controller/policy engine can reject images failing provenance policy before Pods are created.

**Never deploy solely by mutable tag** when audit requirements demand knowing the exact running bytes. Record the digest in deployment records to tie runtime workloads back to release evidence.

## 22. Common Mistakes

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Storing only a Git SHA | Does not identify artifact bytes | Record subject digest and provenance |
| Storing only a SHA-256 sidecar | Does not identify who built the file | Verify signed attestations |
| Using image tags instead of digests | Tags can be moved | Deploy image@sha256 |
| Attesting a JAR then uploading a different JAR | Subject digest no longer matches | Upload the exact attested file |
| Calling an SBOM provenance | SBOMs describe components, not builders | Generate both |
| Unsigned provenance JSON | Can be edited arbitrarily | Use signed envelopes and verify |
| Checking only the signature | Right signer might still violate source/policy rules | Enforce repo, workflow, ref, builder, predicate |
| Trusting predicate fields blindly | A compromised workflow can emit false fields | Trust builder/certificate and isolate signing |
| Putting secrets in build args | Can leak into logs/metadata | Use secure secret mounts/bindings |
| Using PR workflows to sign releases | Untrusted code can influence the signer | Separate PR build/test from release signing |
| Using JAR SBOM alone for images | Misses OS/JRE/buildpack packages | Generate a separate image SBOM |
| Using unpinned mutable builder tags | Rebuilds may use a different builder | Pin version/digest and record builder |
| Deleting attestations with old images | Loses audit evidence | Manage retention/referrers/bundles |
| Treating local Docker Image ID as registry digest | Not the same identifier | Capture manifest digest from registry/build output |
| Confusing image index with platform manifest | Mismatched subject comparison | Record exact platform/digest type |
| Claiming a SLSA level from tool usage alone | Tools do not satisfy all requirements | Assess builder and verification controls |

## 23. Checklist for a Provenance-Backed Release

### Source and Build
- [ ] Built from a finalized commit/tag.
- [ ] Clean working tree or all changes recorded.
- [ ] Maven Wrapper/JDK/plugin versions managed.
- [ ] Dependencies resolved from approved repositories.
- [ ] Workflow and builder identities defined.
- [ ] Untrusted PRs have no release signing/publish permissions.

### Artifact and SBOM
- [ ] Tests/build checks PASS before signing.
- [ ] Artifact files identified by SHA-256.
- [ ] CycloneDX/SPDX SBOM generated with accurate scope.
- [ ] Separate image SBOM generated if releasing a container.
- [ ] SBOM format/schema and digest recorded.

### Provenance and Signatures
- [ ] Statement subject points to the exact artifact digest.
- [ ] Predicate type matches SLSA provenance v1 or chosen policy.
- [ ] Builder/workflow identity verified.
- [ ] Source repository/ref/commit match the release.
- [ ] Signature/certificate/issuer/transparency evidence PASS.
- [ ] Build inputs and resolved dependencies satisfy policy.

### Publish and Deploy
- [ ] Exact attested bytes uploaded.
- [ ] Release evidence index stores artifact digest and attestation URL/bundle.
- [ ] Container images referenced by digest.
- [ ] Consumers verify before installing/deploying.
- [ ] Admission/deployment policy rejects non-compliant artifacts.
- [ ] Attestations, SBOMs, and release records retained per retention policy.

## 24. Self-Check Exercises

**Question 1.** Why can't a Git commit SHA replace a JAR SHA-256?

**Answer:** A commit SHA identifies a source tree; a JAR SHA-256 identifies the built binary bytes. The same commit can yield different binaries if toolchain, dependencies, or inputs change.

**Question 2.** How do provenance and an SBOM differ?

**Answer:** Provenance describes how an artifact was built; an SBOM lists components inside the artifact/scanned scope. A release should include both when required by policy.

**Question 3.** Why must the digest be placed inside the subject?

**Answer:** The subject binds the attestation to the exact bytes. Using only a name or tag allows swapping in a different artifact under the same name.

**Question 4.** Does a valid signature on an attestation guarantee all claims are true?

**Answer:** No. You must trust the builder identity and verify predicate contents, workflow origin, trust boundaries, and input policies.

**Question 5.** Why should signer-workflow be checked?

**Answer:** To ensure the attestation was signed by the exact release workflow or a trusted reusable workflow, not just any arbitrary workflow in the repository.

**Question 6.** Can a JAR's SBOM be used for a container image?

**Answer:** It can describe Maven dependencies, but it is usually insufficient for the entire image because base OS, JRE, and native packages fall outside the Maven graph.

**Question 7.** Why is deploying by image digest better than by tag?

**Answer:** A digest identifies exact manifest content. A tag is a mutable reference that can be moved to a different image.

**Question 8.** Are BuildKit provenance and GitHub signed attestations the same thing?

**Answer:** No. BuildKit produces build metadata attestations; GitHub Artifact Attestations adds signed identity/trust mechanisms. They can complement each other, and you must track where each is stored.

**Question 9.** After attesting, may you rebuild and upload a new JAR under the same name?

**Answer:** Not if you want the link to remain valid. The new file can have a different digest; you must create a fresh attestation and update release evidence.

**Question 10.** Can you claim SLSA Build Level 3 solely because your workflow uses actions/attest@v4?

**Answer:** No. You must also satisfy requirements for trusted builders, isolation, input/provenance completeness, and other controls.

## 25. Official References

- SLSA v1.2 — Build Provenance: https://slsa.dev/spec/v1.2/build-provenance
- SLSA — Verifying Artifacts: https://slsa.dev/spec/v1.2/verifying-artifacts
- in-toto Attestation Framework: https://github.com/in-toto/attestation
- in-toto Predicate — CycloneDX: https://github.com/in-toto/attestation/blob/main/spec/predicates/cyclonedx.md
- GitHub Actions — Using artifact attestations: https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations
- GitHub CLI — gh attestation verify: https://cli.github.com/manual/gh_attestation_verify
- GitHub Actions — actions/attest: https://github.com/actions/attest
- GitHub Actions — Secure use / pin actions: https://docs.github.com/en/actions/reference/security/secure-use
- Sigstore Cosign — verify-attestation: https://github.com/sigstore/cosign/blob/main/doc/cosign_verify-attestation.md
- OCI Image Specification — Content descriptors and digests: https://github.com/opencontainers/image-spec/blob/main/descriptor.md
- OCI Image Specification — Image manifest: https://github.com/opencontainers/image-spec/blob/main/manifest.md
- Docker — Build attestations: https://docs.docker.com/build/metadata/attestations/
- Docker Buildx — build provenance and SBOM options: https://docs.docker.com/reference/cli/docker/buildx/build/
- CycloneDX Maven Plugin — makeAggregateBom: https://cyclonedx.github.io/cyclonedx-maven-plugin/makeAggregateBom-mojo.html
- CycloneDX — SBOM standard: https://cyclonedx.org/