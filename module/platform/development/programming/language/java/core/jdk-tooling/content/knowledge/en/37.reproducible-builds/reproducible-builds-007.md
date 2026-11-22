# Artifact Provenance for Java Builds

## 1. What is artifact provenance?

**Artifact provenance** is a set of verifiable information that tells where a software artifact was created, by which process, on which build platform, and with which inputs.

For a JAR file, provenance helps the recipient answer:

- Which project, version, and release does this artifact belong to?
- Which repository and commit was it built from?
- Which workflow, Maven/Gradle, JDK, and compiler ran?
- Which dependencies, plugins, toolchains, and build images were involved?
- Was the artifact modified after the build or after release?
- Who or which system attested to that information?

Provenance is useful in release engineering, auditing, incident investigation, dependency vulnerability management, and software supply chain control. It helps users determine whether a running artifact is indeed an approved build.

A filename like `service-1.2.3.jar` or a Maven coordinate `com.example:service:1.2.3` only describes a logical identity. To identify the exact bytes, a cryptographic digest such as SHA-256 is required.

## 2. Distinguishing checksum, signature, SBOM, and provenance

These types of metadata address different questions:

| Component | Question answered | What it proves |
|---|---|---|
| Checksum | Does the current file have the same bytes as a known digest? | Integrity against a trusted digest. |
| Digital signature | Who or which system signed these bytes? | Authenticity of the signature and integrity of the payload. |
| SBOM | Which components does the artifact contain or depend on? | The inventory of components and dependencies within the SBOM scope. |
| Build provenance | From which source, builder, and process was the artifact created? | Claims about the source and how it was built, if the attestation is verified. |
| Reproducible build | Does rebuilding with the same inputs produce the same bytes? | Reproducibility of the output under controlled conditions. |

None of these components completely replaces the others.

A checksum does not say who created the artifact. A signature alone does not say which commit the artifact was built from. An SBOM does not prove the artifact was built by a trusted CI. Provenance alone does not guarantee that dependencies are safe. A reproducible build does not prove the build process used approved source.

A trustworthy release typically combines an artifact digest, an SBOM, and signed attestations, then applies verification policies before use.

## 3. Identifying artifacts with Maven coordinates and digests

Maven coordinates consist of:

- `groupId`: the group or namespace of the project.
- `artifactId`: the name of the artifact.
- `version`: the release version.
- `classifier`: an additional classifier, if any.
- `type/extension`: the file type, such as jar, pom, or war.

For example:

~~~text
com.example:payment-service:1.2.3
com.example:payment-service:1.2.3:tests
com.example:payment-service:1.2.3:jar
~~~

Coordinates help locate an artifact in a repository. However, an improperly managed repository may allow overwriting the same coordinate. Therefore, consumers need to verify the SHA-256 of the actual file.

Example on Linux:

~~~bash
sha256sum target/payment-service-1.2.3.jar
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 target\payment-service-1.2.3.jar
~~~

A digest is a fingerprint of the bytes. If even a single byte changes, the SHA-256 almost certainly changes.

In an attestation, the artifact is placed in the `subject` field along with its digest. The verifier must compute the digest of the received file and compare it against the signed digest. Do not rely solely on the filename or version string.

## 4. Data to record for a build

Useful provenance typically contains the following groups of information:

| Group | Data to record |
|---|---|
| Artifact | Name, Maven coordinates, file type, SHA-256. |
| Source | Repository URI, commit SHA, tag/ref, source tree state. |
| Build definition | Workflow path, POM/Gradle files, build type, build parameters. |
| Builder | CI platform identity, runner or build image, builder version. |
| Toolchain | JDK vendor/version, Maven/Gradle Wrapper, compiler and plugin versions. |
| Dependencies | Dependency URI, version, package URL, digest when available. |
| Invocation | Run ID, start/end timestamps, workflow URL or log reference. |
| Outputs | JAR/WAR, SBOM, checksum file, provenance bundle, and byproducts to retain. |

Not every field is automatically recorded by every build platform. Distinguish between data verified by the platform and data self-reported by scripts inside the repository.

Do not include passwords, access tokens, private keys, credentials, or secret environment variables in provenance. External parameters must be inspected by the consumer because they can be influenced by the workflow caller.

## 5. Source identity: repository, ref, and commit

A branch name like `main` can change. A tag can also be moved if the repository does not protect tags. To trace a specific build, an immutable commit SHA must be recorded.

In a local repository:

~~~bash
git rev-parse HEAD
git status --short
git submodule status
~~~

A release build should verify that the source tree is clean or explicitly record uncommitted changes if policy allows. Do not build a release from a working tree with uncommitted files while provenance only records the HEAD commit.

In GitHub Actions, `GITHUB_SHA` provides the commit associated with the workflow event. It can be passed to Maven:

~~~bash
./mvnw -B -ntp -Dsource.revision="$GITHUB_SHA" clean verify
~~~

For tag releases, verify that the tag points to the reviewed commit. Record the repository URI, ref, and commit digest in provenance. The commit SHA identifies the exact source revision; the ref helps understand which branch or tag triggered the build.

If the project uses Git submodules, source bundles, or generated code downloaded from elsewhere, record those source inputs in resolved dependencies or appropriate byproducts.

## 6. Distinguishing build JVM, compiler, and runtime in provenance

A Java build may use multiple JDKs:

- Build JVM running Maven or Gradle.
- Compiler toolchain running `javac`.
- Test launcher running unit/integration tests.
- Runtime JDK running the application after deployment.

Recording a single `java -version` line is not enough to describe the entire build. Record the JDK toolchain that the compiler and test tasks actually use.

Data to record includes:

~~~text
Build JVM: Azul Zulu 24.0.2
Compiler toolchain: Amazon Corretto 17.0.15
Java release: 17
Maven Wrapper: 3.9.12
Maven Compiler Plugin: 3.13.0
~~~

These are examples of distinct fields, not mandatory configuration. Values must be taken from the actual logs/toolchain of each build.

Similarly, if using containers, record the image digest instead of just a tag like `maven:3.9-eclipse-temurin-17`. Tags can be updated; the digest identifies the image bytes.

## 7. What is an SBOM?

A **Software Bill of Materials (SBOM)** is a structured inventory of the components that make up a software product. For a Java application, an SBOM typically records:

- The root component of the project.
- Direct dependencies.
- Transitive dependencies.
- Version and package URL (PURL).
- License and supplier when data is available.
- Component hashes if the tool can collect them.
- Dependency relationships between components.

An SBOM supports vulnerability scanning, license review, dependency impact analysis, and incident response. When a library vulnerability is disclosed, operations teams can find which artifacts contain the affected version.

An SBOM does not by itself prove that the artifact was built from that dependency list. The SBOM must be bound to the artifact by digest and signed/attested so consumers can verify it belongs to the right release.

## 8. CycloneDX and SPDX

Two common SBOM formats:

| Format | Characteristics |
|---|---|
| CycloneDX | Focused on components, dependencies, vulnerabilities, and supply chain use cases. |
| SPDX | ISO/IEC standard, strong in package, file, license, and software composition information. |

Choose the format based on the SBOM-consuming system and organizational policy. Avoid generating two different SBOMs for the same artifact without a synchronization and verification process.

An SBOM should clearly specify:

- Schema version.
- Root component metadata.
- The tool that generated the SBOM.
- Creation timestamp.
- Scope of included dependencies.
- Excluded dependencies and reasons if needed.

For example, an application SBOM may exclude test-scope dependencies. If an inventory for the build environment or test supply chain is needed, generate an additional SBOM with the appropriate scope. An application SBOM does not automatically include all Maven plugins, JDKs, and CI tools.

## 9. Generating a CycloneDX SBOM with Maven

The CycloneDX Maven Plugin can generate an SBOM from a Maven project's dependency tree. The plugin supports per-module BOMs and an aggregate BOM for multi-module builds.

Example configuration:

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
    <includeTestScope>false</includeTestScope>
  </configuration>
</plugin>
~~~

After running:

~~~bash
./mvnw -B -ntp clean package
~~~

The plugin generates:

~~~text
target/bom.json
~~~

With plugin 2.9.3, the verification run in this article generates CycloneDX schema 1.6. Newer plugins may support newer schemas; check compatibility with consumers before upgrading the version.

The `makeBom` goal generates a BOM per Maven module. The `makeAggregateBom` goal generates an aggregate BOM at the reactor root and can also generate per-module BOMs. Choose the goal that fits the project structure.

By default, the plugin attaches the SBOM as an additional artifact during install/deploy. Attachment can be disabled if the pipeline manages SBOMs separately, but ensure the SBOM is stored with the release and does not lose its link to the artifact.

## 10. Reading and inspecting an SBOM

Inspect CycloneDX JSON metadata:

~~~bash
jq '{bomFormat, specVersion, metadata, componentCount: (.components | length)}' target/bom.json
~~~

List dependencies:

~~~bash
jq -r '.components[] | [.name, .version, .purl] | @tsv' target/bom.json
~~~

Find a specific component:

~~~bash
jq -r '.components[] | select(.name == "commons-lang3")' target/bom.json
~~~

On Windows PowerShell:

~~~powershell
$sbom = Get-Content target\bom.json -Raw | ConvertFrom-Json
$sbom.bomFormat
$sbom.specVersion
$sbom.components | Select-Object name, version, purl
~~~

Inspecting an SBOM is not just confirming the file exists. Check the correct project/version, key dependencies, scope, schema, and component count. For multi-module builds, confirm the aggregate BOM includes all modules.

If a dependency is downloaded or added outside the Maven dependency graph—for example, a script downloading a binary during the build—the default SBOM may not contain it. Supplement the data with appropriate tools and clearly document the coverage scope.

## 11. SLSA Build Provenance

SLSA is a framework for describing and evaluating the level of software supply chain protection. Build provenance is an attestation describing how an artifact was created.

In SLSA provenance:

- `subject`: the output artifact and its digest.
- `buildDefinition`: how the build was initiated and its inputs.
- `buildType`: definition of the build process type.
- `externalParameters`: parameters provided externally to the build platform.
- `resolvedDependencies`: resolved source, dependencies, and input artifacts.
- `runDetails.builder.id`: trusted build platform identity.
- `metadata.invocationId`: identifier of the build run.
- `startedOn`, `finishedOn`: build timestamps.

The predicate type for SLSA Build Provenance is:

~~~text
https://slsa.dev/provenance/v1
~~~

This URI keeps the major version while minor specifications may receive compatible updates. The current specification is **SLSA v1.2**.

SLSA provenance tells consumers where, when, and how an artifact was created. The trustworthiness of this information depends on the builder and how the platform generates, signs, and protects provenance. A JSON file written by a script inside the repository does not automatically become trusted provenance.

## 12. In-toto Attestation Framework

The in-toto Attestation Framework defines how metadata is bound to an artifact.

The framework has four layers:

| Layer | Role |
|---|---|
| Predicate | Metadata content following a specific schema, such as SLSA provenance or SBOM. |
| Statement | Binds a subject artifact with a predicate type and predicate. |
| Envelope | Packages and authenticates the attestation, typically via a signature. |
| Bundle | Groups attestations and related verification data. |

A v1 statement uses:

~~~text
https://in-toto.io/Statement/v1
~~~

An attestation must clearly link the subject and digest. If the predicate describes artifact A while the consumer receives artifact B, the digest mismatch must cause verification to fail.

SLSA provenance is a predicate type with a specific schema in the in-toto framework. An SBOM can also be packaged as a separate attestation. This allows provenance and inventory to be checked using different policies.

## 13. Illustrative SLSA statement structure

The example below illustrates the key fields. Illustrative values must be replaced with real build data by a trusted builder; do not sign or publish this example verbatim.

~~~json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "provenance-demo-1.0.0.jar",
      "digest": {
        "sha256": "JAR_SHA256_DIGEST"
      }
    }
  ],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1",
      "externalParameters": {
        "repository": "https://github.com/example/provenance-demo",
        "ref": "refs/tags/v1.0.0"
      },
      "resolvedDependencies": [
        {
          "uri": "git+https://github.com/example/provenance-demo@refs/tags/v1.0.0",
          "digest": {
            "gitCommit": "RESOLVED_COMMIT_SHA"
          }
        }
      ]
    },
    "runDetails": {
      "builder": {
        "id": "BUILDER_ID_PUBLISHED_BY_PLATFORM"
      },
      "metadata": {
        "invocationId": "CI_RUN_ID",
        "startedOn": "2026-11-10T14:00:00Z",
        "finishedOn": "2026-11-10T14:02:00Z"
      }
    }
  }
}
~~~

Points to note:

- `subject.digest.sha256` must be the digest of the released JAR file.
- `resolvedDependencies` must identify the actual commit, not just a branch name.
- `builder.id` must be an identity published and described by the CI platform.
- `buildType` must accurately describe the workflow or build template.
- `invocationId` must link to a specific build log.
- Timestamps should be in UTC and follow the spec's timestamp format.

Do not invent a builder ID and treat it as a verified identity. Consumers need a list of trusted builder identities.

## 14. Builder identity and signer identity

Builder and signer are two distinct roles.

**Builder identity** indicates which system executed the build and is responsible for the accuracy of the provenance.

**Signer identity** indicates who or which service signed the attestation.

One signer may sign provenance for multiple builders. Therefore, the verifier must check the signer-builder pair allowed by policy. A valid signature from an untrusted identity does not make an artifact trustworthy.

With hosted CI, the builder identity is usually defined by the platform. With self-hosted runners, evaluate who manages the runner, how jobs are isolated, how credentials are issued, and whether the runner can retain state from previous builds.

Do not grant provenance signing permissions to every workflow or branch. Release workflows need least privilege, protected environments, and an appropriate review process.

## 15. Hashes and digital signatures

SHA-256 helps detect artifact tampering:

~~~bash
sha256sum target/provenance-demo-1.0.0.jar > target/SHA256SUMS
sha256sum -c target/SHA256SUMS
~~~

On Windows:

~~~powershell
Get-FileHash -Algorithm SHA256 target\provenance-demo-1.0.0.jar
~~~

If the checksum and artifact are downloaded from the same compromised source, an attacker can alter both. Therefore, checksums should be authenticated via a signature or attestation with an independent trust root.

A digital signature binds a signer identity to bytes or an attestation. Consumers need to check:

1. Is the signature valid?
2. Was the certificate/key issued by the expected trust root?
3. Does the signer identity match the expected repository, workflow, or organization?
4. Is the OIDC issuer correct?
5. Does the subject digest in the payload match the artifact?
6. Are the transparency log proof and timestamp valid if the system uses a transparency log?

Checking only the signature without checking the identity can accept artifacts signed by an unwanted workflow or organization.

## 16. Keyless signing with Sigstore

Sigstore supports signing artifacts using an identity authenticated via OpenID Connect (OIDC), commonly called keyless signing.

General flow:

1. CI obtains an OIDC identity token from the identity provider.
2. Fulcio issues a short-lived certificate binding an ephemeral public key to the identity.
3. Cosign signs the artifact using the ephemeral private key.
4. The signature and certificate are stored in a bundle.
5. The Rekor transparency log records the signing event.
6. The consumer verifies the bundle, certificate, identity, issuer, and digest.

Example of signing a file:

~~~bash
cosign sign-blob --yes --bundle artifact.sigstore.json target/provenance-demo-1.0.0.jar
~~~

Verification:

~~~bash
cosign verify-blob target/provenance-demo-1.0.0.jar \
  --bundle artifact.sigstore.json \
  --certificate-identity="https://github.com/OWNER/REPOSITORY/.github/workflows/release.yml@refs/heads/main" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com"
~~~

Replace OWNER, REPOSITORY, and workflow identity with actual values. The identity must match the certificate in the bundle. Do not use overly broad wildcards if policy requires accepting only a specific release workflow.

Keyless signing reduces the need to store long-lived private keys in CI secrets. However, permissions to obtain OIDC tokens and run release workflows still need to be protected.

## 17. Generating artifact provenance on GitHub Actions

GitHub Actions can generate artifact attestations after a build. The workflow needs these permissions:

~~~yaml
permissions:
  contents: read
  id-token: write
  attestations: write
~~~

After the build step, add:

~~~yaml
- name: Attest release JAR
  uses: actions/attest@v4
  with:
    subject-path: target/provenance-demo-1.0.0.jar
~~~

The attestation links the artifact to the workflow, repository, organization, environment, commit SHA, and information from the OIDC token.

An SBOM attestation can also be generated:

~~~yaml
- name: Attest CycloneDX SBOM
  uses: actions/attest@v4
  with:
    subject-path: target/provenance-demo-1.0.0.jar
    sbom-path: target/bom.json
~~~

Artifact provenance and SBOM attestation are two claims with different predicates. Both link to the same artifact subject, allowing consumers to verify the build source and component inventory separately.

In production repositories, pin GitHub Actions by a reviewed full commit SHA rather than relying solely on a version tag like `@v4`. Grant `id-token: write` and `attestations: write` only to the job that actually needs to sign.

According to current GitHub documentation, artifact attestations are available on current plans; Free, Pro, and Team only support public repositories, while private/internal repositories require GitHub Enterprise Cloud. Check plan and visibility requirements before designing the release pipeline.

## 18. Complete Maven workflow example

This illustrative workflow builds Java 17, creates a JAR and SBOM, and then attests both:

~~~yaml
name: Java release

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
      contents: read
      id-token: write
      attestations: write

    steps:
      - uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
          cache: maven

      - name: Verify source and toolchain
        run: |
          test -z "$(git status --porcelain)"
          java -version
          javac -version
          ./mvnw -version
          git rev-parse HEAD

      - name: Build JAR and SBOM
        run: |
          ./mvnw -B -ntp \
            -Dsource.revision="$(git rev-parse HEAD)" \
            clean verify

      - name: Generate JAR provenance
        uses: actions/attest@v4
        with:
          subject-path: target/provenance-demo-1.0.0.jar

      - name: Generate SBOM attestation
        uses: actions/attest@v4
        with:
          subject-path: target/provenance-demo-1.0.0.jar
          sbom-path: target/bom.json

      - name: Publish build outputs
        uses: actions/upload-artifact@v4
        with:
          name: java-release
          path: |
            target/provenance-demo-1.0.0.jar
            target/bom.json
~~~

This is an illustrative workflow; artifact names, versions, branch policies, and release paths must match the actual project. In production environments, pin actions by commit SHA and ensure the workflow only runs from protected tags/branches.

Do not use artifacts from untrusted pull request jobs to create release attestations. Release jobs should build from approved commits in a CI environment with clear trust boundaries.

## 19. Verifying GitHub artifact attestations

Install the GitHub CLI and log in with an identity that has permission to read the repository/attestations. Verify the JAR:

~~~bash
gh attestation verify target/provenance-demo-1.0.0.jar \
  -R OWNER/REPOSITORY
~~~

Verify the SBOM attestation attached to the same JAR:

~~~bash
gh attestation verify target/provenance-demo-1.0.0.jar \
  -R OWNER/REPOSITORY \
  --predicate-type https://cyclonedx.org/bom
~~~

You can view the verified predicate:

~~~bash
gh attestation verify target/provenance-demo-1.0.0.jar \
  -R OWNER/REPOSITORY \
  --format json
~~~

Consumers need to verify the repository, workflow, source ref/commit, builder identity, and subject digest against organizational policy. A valid attestation generated by an unauthorized repository or workflow must still be rejected.

Attestation verification must run on the exact file received. Do not verify a different file and merely trust a similar filename.

## 20. Checking that the SBOM and artifact belong to the same release

A release process should link the JAR and SBOM by digest.

Example release directory files:

~~~text
release/
  provenance-demo-1.0.0.jar
  bom.json
  SHA256SUMS
  provenance.sigstore.json
~~~

Checksum:

~~~bash
sha256sum provenance-demo-1.0.0.jar bom.json > SHA256SUMS
sha256sum -c SHA256SUMS
~~~

In practice, an SBOM attestation should state the artifact subject and sign the claim about the SBOM file. Do not just sign the SBOM standalone while omitting the link to the artifact it describes.

If the SBOM is generated after the JAR has been shaded, repackaged, or signed, make sure the SBOM accurately describes the final artifact and its dependency set. The pipeline should have a single step that determines the final release artifact before computing digests and attesting.

## 21. Reproducible builds and provenance

A reproducible build is the ability to recreate the exact same artifact bytes from the same source and build inputs. Artifact provenance records the inputs and builder so others can inspect or attempt to reproduce the build.

The two concepts complement each other:

- Reproducibility checks whether the output can be recreated.
- Provenance explains which source, tools, and environment were used to create the output.
- Signatures/attestations protect the authenticity of claims and bind claims to the artifact digest.

With Maven, you can use:

~~~xml
<properties>
  <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

The timestamp value must remain stable across builds. In a release pipeline, a stable timestamp can be derived from the source revision according to project policy.

Do not embed the build start time, random invocation ID, or data that changes on each run into the JAR if the goal is to produce a reproducible artifact. Keep invocation and timing information in the provenance sidecar.

## 22. Example Maven project with manifest, SBOM, and executable JAR

Structure:

~~~text
provenance-demo/
  pom.xml
  src/
    main/
      java/
        example/
          ProvenanceDemo.java
~~~

`ProvenanceDemo.java` file:

~~~java
package example;

import org.apache.commons.lang3.StringUtils;

public class ProvenanceDemo {
    public static void main(String[] args) {
        System.out.println("message=" + StringUtils.capitalize("artifact provenance"));
    }
}
~~~

Example POM:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example.provenance</groupId>
  <artifactId>provenance-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    <source.revision>local-demo</source.revision>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.apache.commons</groupId>
      <artifactId>commons-lang3</artifactId>
      <version>3.17.0</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
          <encoding>UTF-8</encoding>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>example.ProvenanceDemo</mainClass>
            </manifest>
            <manifestEntries>
              <Implementation-Title>__DOLLAR__{project.groupId}:__DOLLAR__{project.artifactId}</Implementation-Title>
              <Implementation-Version>__DOLLAR__{project.version}</Implementation-Version>
              <Build-Revision>__DOLLAR__{source.revision}</Build-Revision>
              <Build-Jdk-Spec>17</Build-Jdk-Spec>
            </manifestEntries>
          </archive>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.6.0</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals>
              <goal>shade</goal>
            </goals>
            <configuration>
              <createDependencyReducedPom>false</createDependencyReducedPom>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <mainClass>example.ProvenanceDemo</mainClass>
                </transformer>
              </transformers>
            </configuration>
          </execution>
        </executions>
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
          <includeTestScope>false</includeTestScope>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

In a release pipeline, pass the real source commit via `-Dsource.revision`. The default value `local-demo` is only for running the example on a development machine and is not a trusted source identity.

## 23. Building, running, and inspecting the artifact

Build with Maven Wrapper:

~~~bash
./mvnw -B -ntp -Dsource.revision="$(git rev-parse HEAD)" clean verify
~~~

Run the JAR:

~~~bash
java -jar target/provenance-demo-1.0.0.jar
~~~

Stdout:

~~~text
message=Artifact provenance
~~~

Inspect the manifest:

~~~bash
unzip -p target/provenance-demo-1.0.0.jar META-INF/MANIFEST.MF
~~~

The manifest contains entries such as:

~~~text
Main-Class: example.ProvenanceDemo
Build-Jdk-Spec: 17
Build-Revision: <source-commit-sha>
Implementation-Title: example.provenance:provenance-demo
Implementation-Version: 1.0.0
~~~

Check digests:

~~~bash
sha256sum target/provenance-demo-1.0.0.jar target/bom.json
~~~

Inspect the SBOM:

~~~bash
jq '{bomFormat, specVersion, component: .metadata.component, components}' target/bom.json
~~~

`Build-Revision` in the manifest is useful for traceability, but it can be modified along with the JAR. It does not replace a signature or provenance attestation issued by a trusted builder.

## 24. Project verification results

The sample project was built on Windows 11 with Maven 3.9.12, running on Azul JDK 24.0.2 and compiled with release 17.

Results:

~~~text
BUILD SUCCESS
message=Artifact provenance
bomFormat=CycloneDX
specVersion=1.6
component=provenance-demo:1.0.0
dependencyComponents=1
commons-lang3-present=True
~~~

The manifest recorded:

~~~text
Main-Class: example.ProvenanceDemo
Build-Jdk-Spec: 17
Build-Revision: 0123456789abcdef0123456789abcdef01234567
Implementation-Title: example.provenance:provenance-demo
Implementation-Version: 1.0.0
~~~

Two clean builds were run with the same source revision and the same `project.build.outputTimestamp`. The SHA-256 of the JAR in both runs was identical:

~~~text
77e29ade3aad27f034aea9d9790dfaa8b52d50b35ed6807a344f9c7fc4365f9b
artifact.reproducible=True
~~~

This is the result of the demo project and the specific test environment. It demonstrates that the sample configuration produces a deterministic JAR in this test run; it does not prove that every Maven project or every machine is reproducible.

The CycloneDX plugin printed JSON schema validator warnings about some unrecognized meta keywords, but it still generated the BOM, validated the output, and finished the build successfully.

## 25. Releasing artifacts safely

When releasing, store the artifact and metadata in the same release record:

1. JAR/WAR or container image.
2. SHA-256 digest.
3. SBOM corresponding to the final artifact.
4. Build provenance attestation.
5. SBOM attestation if required by policy.
6. Release notes and source commit.
7. Build logs or invocation ID needed for investigation.

Use immutable release versions and do not overwrite released artifacts. If a fix is needed, release a new version and generate new provenance.

With a Maven repository, you can deploy the JAR, POM, and SBOM classifier. With a container registry, attestations typically link directly to the image digest. Regardless of the repository used, consumers must verify the exact digest of the received artifact.

Retain attestations for at least as long as the artifact remains in use. Once an artifact has been deployed across multiple environments, provenance is also needed for vulnerability response and forensic investigation.

## 26. Verifying provenance against policy

A verifier should perform the following steps:

1. Compute the SHA-256 of the received artifact.
2. Verify the attestation envelope/signature.
3. Check the certificate, signer identity, and OIDC issuer.
4. Compare the subject digest in the attestation with the artifact.
5. Check whether the builder ID is in the trusted list.
6. Check the build type and workflow path.
7. Check that the repository, ref, and commit SHA are allowed.
8. Check that build parameters do not contain values outside policy.
9. Check dependencies/SBOM against vulnerability and license policies.
10. Store verification results for auditing.

A verifier should not accept every builder simply because the signature is valid. Policy must explicitly define the allowed signer-builder pair, repository, workflow, and source branch/tag.

If an attestation is valid but the commit is not in an approved release, the artifact must still be rejected. Similarly, an artifact with a complete SBOM that contains a prohibited dependency may still not be allowed to deploy.

## 27. Artifact provenance in multi-module and container builds

For Maven multi-module builds, generate an aggregate SBOM at the reactor root and link each output to its corresponding module coordinates/digest. An aggregate BOM should not lose the ability to determine which artifact depends on which component.

For container builds, provenance needs to identify the image digest, base image digest, build context, Dockerfile or build recipe, build args, and platform/architecture. An image tag is not sufficient because tags can change.

If a JAR is packaged into a container, there can be two layers of provenance:

- JAR provenance: source commit, Maven, JDK, dependencies, and compiler.
- Container provenance: base image, Dockerfile, layers, build tool, and image digest.

A JAR's SBOM and a container's SBOM have different scopes. A container SBOM may include OS packages and runtime libraries that the Maven project SBOM does not record.

## 28. Common risks

| Mistake | Risk | Mitigation |
|---|---|---|
| Publishing only SHA-256 | An attacker alters both the file and the checksum. | Sign the checksum or use a signed attestation. |
| Only signing the artifact | Unknown which source and builder created the file. | Include build provenance. |
| Generating an SBOM without binding a digest | Unclear which artifact the SBOM describes. | Attest the SBOM with the artifact subject and digest. |
| Using a branch name as source identity | Branches can change. | Record an immutable commit SHA. |
| Trusting manifest `Build-Revision` | The manifest can be edited along with the JAR. | Verify signed provenance. |
| Using non-isolated self-hosted runners | Previous builds may leave behind state or credentials. | Use ephemeral runners, least privilege, and workspace controls. |
| Accepting any signer | An attacker can use another identity to sign an artifact. | Check the specific issuer and signer identity. |
| Accepting any builder ID | Provenance from a weak builder may be mistakenly trusted. | Allowlist builders and signer-builder pairs. |
| SBOM with only compile dependencies | Misses test/build/native tools or runtime packages. | Clearly document scope and generate supplementary inventories when needed. |
| Overwriting the same Maven release version | Consumers cannot tell which bytes are official. | Use immutable releases and a new version on changes. |
| Putting secrets into provenance | Leaks credentials or internal information. | Record only necessary parameters and strip secrets. |
| Writing JSON yourself and calling it trusted provenance | No guarantee about the builder or signature. | Have the CI platform generate and sign the attestation. |

## 29. Investigating incidents using provenance

When a dependency has a vulnerability or an artifact is suspected:

1. Identify the artifact by SHA-256.
2. Retrieve the provenance and SBOM attached to that digest.
3. Check the repository, commit, workflow, builder, and invocation ID.
4. Search for the affected dependency's version/PURL in the SBOM.
5. Identify which artifacts/releases/containers contain that dependency.
6. Compare with earlier and later builds to find changes.
7. Verify signatures and transparency records.
8. Collect build logs, dependency resolution data, and release history.
9. Rebuild from approved source if necessary.
10. Release a new version, new SBOM, and new attestation.

Provenance helps narrow the scope of an investigation. It does not replace vulnerability scanning, code review, runtime monitoring, or incident response.

## 30. Checklist for Java artifact releases

- [ ] Artifact has Maven coordinates and an immutable version.
- [ ] Source repository URI and commit SHA are recorded.
- [ ] Source tree is clean or changes are controlled.
- [ ] JDK build JVM and compiler toolchain are clearly recorded.
- [ ] Maven/Gradle Wrapper and plugin versions are pinned.
- [ ] Build image/base image digest is recorded when using containers.
- [ ] Dependency tree is inventoried using an SBOM.
- [ ] SBOM schema, scope, and root component have been checked.
- [ ] SHA-256 is computed on the final artifact after packaging/signing/shading.
- [ ] Provenance subject contains the digest of the exact released artifact.
- [ ] Builder ID and signer identity are in the trust policy.
- [ ] Attestation envelope/signature is verified.
- [ ] Repository, workflow, ref, and commit are checked.
- [ ] SBOM attestation links to the correct artifact subject.
- [ ] Artifact and metadata are stored in an immutable location.
- [ ] No secrets are present in the manifest, SBOM, provenance, or logs.
- [ ] Consumers can re-verify the artifact after downloading.

## 31. References

- SLSA v1.2 — Build Provenance: https://slsa.dev/spec/v1.2/build-provenance
- SLSA — Verifying Artifacts: https://slsa.dev/spec/v1.2/verifying-artifacts
- in-toto Attestation Framework: https://github.com/in-toto/attestation
- CycloneDX Maven Plugin: https://cyclonedx.github.io/cyclonedx-maven-plugin/
- CycloneDX Maven Plugin source and schema support: https://github.com/CycloneDX/cyclonedx-maven-plugin
- GitHub — Artifact Attestations: https://docs.github.com/en/actions/concepts/security/artifact-attestations
- GitHub — Generate and verify build provenance: https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations
- Sigstore Cosign Quickstart: https://docs.sigstore.dev/quickstart/quickstart-cosign/
- Sigstore — Verifying Signatures: https://docs.sigstore.dev/cosign/verifying/verify/

Artifact provenance enables consumers to trace a JAR back to its source, dependencies, build workflow, and builder. For that claim to have security value, bind the artifact by digest, generate attestations on a trusted CI, sign with a verifiable identity, and enforce policy checks before deployment.
