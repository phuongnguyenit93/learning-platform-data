# Verifying Java Artifacts: Checksums, Signatures, and Validity

## Objectives

After this lesson, you will be able to explain what artifact verification is; distinguish between identity, integrity, authenticity, and provenance; check coordinates and download sources; compute SHA-256/SHA-512 on Linux and Windows; verify JAR signatures with jarsigner and PGP detached signatures with GPG; enable strict checksums in Maven and dependency verification in Gradle; inspect structure, manifest, classes, resources, and module descriptors; verify dependency graphs; run consumer tests from published artifacts; store evidence in CI; and troubleshoot checksum, signature, metadata, repository, or artifact content errors.

## 1. What Is Artifact Verification?

An artifact is a file produced or distributed from a build, such as a JAR, WAR, EAR, ZIP, POM, native binary, container image, or other package.

**Artifact verification** is the process of checking whether the received file is the expected artifact, preserves its contents, comes from a trusted publisher, and meets usage requirements.

A successful download command or HTTP 200 only indicates that the server returned data. It does not prove that the file:

- Belongs to the right group, artifact, and version.
- Has the exact same bytes as the released artifact.
- Was signed by the expected publisher.
- Has the right contents and metadata.
- Can be compiled or run by a consumer.
- Was built from an approved source revision and workflow.

Verification is needed on both sides:

1. **Producer:** checks the artifact after the build, before signing and publishing.
2. **Consumer:** checks the file downloaded from the repository before using it or including it in a release.

An artifact already checked by the producer can still be altered in transit or in the repository. Consumers must verify it again according to their own trust policy.

## 2. Layers of Artifact Verification

Each layer answers a different question.

| Layer | Question | Evidence |
|---|---|---|
| Identity | Is this the right artifact/version? | Coordinates, repository URL, POM |
| Integrity | Do the bytes match the expected fingerprint? | SHA-256/SHA-512 |
| Authenticity | Who signed the artifact? | JAR signature, PGP signature |
| Provenance | From which source/workflow was the artifact built? | Build attestation |
| Structure | Does the file have the expected contents? | jar, unzip, manifest |
| Compatibility | Can the consumer use it? | javap, jdeps, compile/test |
| Security | Are there vulnerabilities or policy violations? | SBOM, vulnerability scan |

These layers complement one another:

- A matching checksum alone does not prove who published the file.
- A valid signature alone does not prove the version is safe or free of vulnerabilities.
- Provenance recording the build source does not automatically prove the output is reproducible.
- A JAR that opens cleanly does not automatically prove API compatibility with the consumer.

## 3. Confirm Identity Before Checking Bytes

With Maven, record the groupId, artifactId, version, packaging/extension, classifier, and repository.

Example:

~~~text
com.acme.platform:domain:1.0.0
com.acme.platform:domain:jar:sources:1.0.0
com.acme.platform:domain:jar:javadoc:1.0.0
~~~

The main artifact, sources, and Javadoc may share the same version yet be different files. Do not compare the checksum of sources.jar against the checksum of the main JAR.

With Gradle, check the dependency declaration, selected component, and variant. A dependency may select a variant based on usage, attributes, platform, or capability. A filename in the cache is not the sole evidence of which variant was selected.

Record the actual repository URL: Maven Central, internal repository manager, centrally declared Gradle repository, mirror/proxy, or staging repository. The same coordinates can exist in multiple repositories and return different bytes.

Do not include usernames, passwords, or tokens from repository URLs in audit logs. Redact credentials before saving evidence.

## 4. Checksums and Hashes

A hash function takes data of arbitrary length and produces a fixed-length digest. SHA-256 produces a 256-bit digest; SHA-512 produces a 512-bit digest.

Comparison workflow:

1. Compute the digest of the file you have.
2. Obtain the expected digest from a trusted source.
3. Compare the two values.
4. If they differ, stop using the artifact and investigate.

Illustrative example:

~~~text
artifact.jar
SHA-256: 9f86d081884c7d659a2feaa0c55ad015...
~~~

The string above only illustrates digest formatting, not the checksum of a specific JAR.

Prefer SHA-256 or SHA-512 for new integrity checks. Do not use MD5 or SHA-1 as an anti-tampering mechanism. If an older repository only provides SHA-1/MD5, understand that they mainly detect transfer errors; supplement them with strong checksums or independently verified signatures.

### Checksum Does Not Mean Authenticity

Suppose a server provides both:

~~~text
domain-1.0.0.jar
domain-1.0.0.jar.sha256
~~~

If an attacker can replace both the JAR and the .sha256 file, the two files will still match. A checksum fetched from the same delivery source only proves the two files are consistent according to that source; it does not by itself prove the publishing source is trustworthy.

To verify authenticity, you need a checksum obtained from an independent trusted channel or a digital signature bound to a verified public key.

## 5. Computing and Checking SHA-256

Linux:

~~~bash
sha256sum domain-1.0.0.jar
~~~

macOS:

~~~bash
shasum -a 256 domain-1.0.0.jar
~~~

If a reference checksum file in standard format is available:

~~~bash
sha256sum --check domain-1.0.0.jar.sha256
~~~

Sample checksum file:

~~~text
9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08  domain-1.0.0.jar
~~~

The digest above only illustrates the format. Actual releases must use the value published for that exact artifact.

Windows PowerShell:

~~~powershell
Get-FileHash .\domain-1.0.0.jar -Algorithm SHA256
~~~

Compare with the expected digest:

~~~powershell
$expected = 'REPLACE_WITH_TRUSTED_SHA256'
$actual = (Get-FileHash .\domain-1.0.0.jar -Algorithm SHA256).Hash

if ($actual -ne $expected) {
    throw 'Artifact SHA-256 mismatch'
}

Write-Output 'SHA256_OK'
~~~

The REPLACE_WITH_TRUSTED_SHA256 value must be replaced with the digest obtained from release metadata or an independently verified channel.

Stdout on match:

~~~text
SHA256_OK
~~~

On mismatch, the script fails with an error so the pipeline does not continue using the artifact. Do not generate a checksum file from the file you just downloaded and treat that as verification; generating a digest only records the current contents.

## 6. Verifying Digital Signatures

A digital signature combines a hash of the content with the signer's private key. Consumers use the public key to verify the signature.

If the signature is valid, the signed content has not been altered after signing and the signature was created using the private key corresponding to that public key.

To trust the signer, you must also confirm that the public key/certificate genuinely belongs to the expected publisher. A valid signature from an untrusted key does not make the artifact trustworthy.

| Signature Type | Example | How to Verify |
|---|---|---|
| JAR signature | .SF, .RSA, .DSA, or .EC in META-INF | jarsigner -verify |
| Detached OpenPGP | .asc file next to JAR/POM | gpg --verify |

The two signature types have different formats and trust workflows. Do not use jarsigner to check a PGP .asc file, and do not use GPG as a substitute for JAR entry signature verification.

## 7. Verifying JAR Signatures with jarsigner

The JDK provides the jarsigner tool to sign and verify Java Archives.

~~~bash
jarsigner -verify -strict -verbose -certs domain-1.0.0.jar
~~~

- -verify: verifies the JAR signature.
- -strict: treats severe warnings as errors.
- -verbose: displays the status of each entry.
- -certs: displays the signer's certificate.

When the signature is valid, the output may contain:

~~~text
jar verified.
~~~

If the JAR is not signed, the tool may report JAR unsigned. If a signed entry was modified after signing, verification will fail.

Verbose output may show:
- s: the entry's signature has been verified.
- m: the entry is listed in the manifest.
- k: the signer certificate was found in the checked keystore.

Read all warnings and certificate information, not just the jar verified. line.

### Checking Whether the Signer Is Trusted

You can use a truststore containing signer certificates verified by your organization:

~~~bash
jarsigner -verify -strict -verbose -certs \
  -keystore trusted-signers.p12 \
  domain-1.0.0.jar trustedSigner
~~~

trusted-signers.p12 and the alias trustedSigner are examples. The truststore must be built from certificates/public keys verified through an independent trust process.

Distinguish three questions:

1. Does the signature match the content?
2. Is the certificate valid under the trust policy?
3. Does the certificate belong to the publisher the project expects?

Certificates have a validity period. A signature with a timestamp from a trusted TSA can help confirm the signature was created while the certificate was still valid. Check warnings for expired/not-yet-valid certificates, unvalidated chains, self-signed signers, key usage not permitting code signing, weak algorithms, or invalid timestamp authorities.

JAR signatures verify signed entries through the manifest and signature files. Files added after signing may not be part of the signed entry set. Package completely before signing. After signing, do not edit, add, or replace resources in the JAR; if changes are needed, rebuild the artifact and sign again.

## 8. Verifying Detached PGP Signatures

Some repositories, including Maven Central, distribute detached PGP signatures:

~~~text
domain-1.0.0.jar
domain-1.0.0.jar.asc
domain-1.0.0.pom
domain-1.0.0.pom.asc
~~~

Verify:

~~~bash
gpg --verify domain-1.0.0.jar.asc domain-1.0.0.jar
~~~

Before trusting the result, obtain the publisher's public key from an official source and verify its fingerprint through an independent channel:

~~~bash
gpg --show-keys --with-fingerprint publisher-public-key.asc
~~~

Compare the full fingerprint against the information published by the publisher or organization. Then import the verified key into the appropriate keyring and re-run verification.

Do not rely solely on display name, email, or short key ID. Names and emails in a key can be self-declared; the full fingerprint is the identifier to verify.

When the signature is valid, GPG may display:

~~~text
Good signature from "Example Publisher"
~~~

Good signature means the signature matches the key. It does not by itself prove the key belongs to the right publisher. Verify the fingerprint and trust policy.

JAR signatures verify entries inside a Java Archive. Detached PGP signatures commonly accompany artifacts/POMs in Maven repositories and can sign many file types. A release may provide both checksums and signatures. Not every JAR is signed with jarsigner; follow the release policy of the repository/project.

## 9. Verifying Dependency Checksums in Maven

Maven Resolver can fetch artifact checksums from the repository and compare them with the downloaded bytes.

The Maven CLI supports strict checksum mode:

~~~bash
./mvnw -C --batch-mode verify
~~~

-C is equivalent to --strict-checksums: the build fails if the received checksum does not match the artifact. Lax mode -c only warns on mismatch and is unsuitable for release gates requiring fail-closed behavior.

Checksums downloaded alongside an artifact over the same repository/transport can detect corrupted files or inconsistent changes. They do not by themselves prove the checksum came from a trusted publisher.

Maven Resolver distinguishes transport checksums from trusted checksums. For stricter requirements, you can manage trusted checksums independently in source control or verify PGP signatures.

### Trusted Checksums in Maven Resolver

Maven Resolver supports trusted checksum sources. With Maven 3.9.x, you can configure summary checksum files and fail-on-missing trusted checksums according to the official documentation.

General workflow:

1. Verify the initial artifact/checksum from a trusted source.
2. Record the trusted SHA-512 in a summary file in the project.
3. Review the checksum file and repository source.
4. Commit trusted checksums alongside the source code.
5. Run builds in verify mode without enabling record mode.
6. When a dependency changes legitimately, review the new checksum before updating.

Do not generate trusted checksums and automatically trust them right away. If the initial artifact was already altered, recording it can stamp tampered content as trusted.

## 10. Verifying Dependencies in Gradle

Gradle supports dependency verification for resolved dependencies and plugins. Two main methods:

- **Checksum:** checks the bytes of the artifact.
- **Signature:** checks that the artifact was signed by a declared trusted key.

Both can be used together.

Generate verification metadata using a task that actually resolves the dependencies/plugins to be checked:

~~~bash
./gradlew --write-verification-metadata sha256,pgp build
~~~

Gradle creates the file:

~~~text
gradle/verification-metadata.xml
~~~

The file can contain checksums and trusted public key metadata for observed artifacts.

Then:

1. Open and review the metadata file.
2. Verify the keys/fingerprints with the publisher.
3. Check transitive dependencies and plugins.
4. Commit the reviewed metadata.
5. Run normal builds so Gradle performs verification.

If you only resolve compile dependencies while skipping test, runtime, plugin, or other configurations, the metadata may miss artifacts when another pipeline runs. Run a task representative of all configurations/variants that need protection.

The metadata generation command records artifacts from the current repository. If the repository returned the wrong file or an artifact was compromised, the new checksum could cause tampered content to be trusted. Review every change, verify keys/checksums from an independent source, and do not blindly accept new metadata just because Gradle generated the file.

Dependency verification does not replace vulnerability scanning. It answers whether an artifact has the trusted bytes/key; it does not answer whether a dependency has a CVE, an incompatible license, or malicious code from the original release.

## 11. Inspecting JAR Structure and Contents

List entries:

~~~bash
jar --list --file domain-1.0.0.jar
~~~

Test the ZIP archive:

~~~bash
unzip -t domain-1.0.0.jar
~~~

View the manifest:

~~~bash
unzip -p domain-1.0.0.jar META-INF/MANIFEST.MF
~~~

Check expected public packages/classes, resource configurations, service provider files in META-INF/services, manifest attributes, version/build metadata, and module-info.class if using JPMS.

Ensure there are no .env files, credentials, private keys, local sources, or unintended debug files; no duplicate classes or files outside the publication scope.

For JARs with a manifest, you can inspect:

~~~text
Implementation-Title
Implementation-Version
Specification-Title
Specification-Version
Automatic-Module-Name
Main-Class
Class-Path
Multi-Release
~~~

Not every artifact has all attributes. Manifest values should match the project's release metadata.

Inspect the module descriptor:

~~~bash
jar --describe-module --file domain-1.0.0.jar
~~~

If using JPMS, confirm the module name, requires, exports, opens, uses, and provides match the design. If the JAR has no module-info.class, it can still be a valid library on the classpath or an automatic module. Do not treat a missing descriptor as an error if the project does not require JPMS.

## 12. Checking Java Bytecode and API Compatibility

A JAR may open cleanly yet still be incompatible with the runtime or consumer.

Use javap:

~~~bash
javap -verbose -classpath domain-1.0.0.jar \
  com.acme.platform.domain.Customer
~~~

In the output, look for the major version.

| Java release | Class file major version |
|---:|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

The class file version indicates the bytecode level. It does not prove the artifact only uses APIs from that release if the compiler was not properly configured with --release.

Use jdeps:

~~~bash
jdeps --summary domain-1.0.0.jar
~~~

Inspect detailed dependencies:

~~~bash
jdeps --recursive --verbose:class domain-1.0.0.jar
~~~

For modular JARs:

~~~bash
jdeps --check com.acme.platform.domain --module-path libs
~~~

Paths and module names must match the real project. The results help detect unwanted dependencies, missing modules, or packages depending on internal APIs.

View public signatures:

~~~bash
javap -classpath domain-1.0.0.jar \
  -public com.acme.platform.domain.Customer
~~~

For library releases, you can use japicmp or Revapi to compare the new artifact with the previous version. The tool must be configured with the right baseline, filters, and policy to classify breaking changes.

Do not confuse API compatibility with file integrity: two JARs with different checksums can still be API-compatible; two JARs with the same coordinates can also differ unexpectedly in API.

## 13. Checking Dependency Graph and Metadata

Library artifacts typically need a POM or Gradle Module Metadata so consumers know transitive dependencies and variants.

Maven: inspect the published POM:

~~~bash
cat domain-1.0.0.pom
~~~

Check GAV, packaging, dependencies and scopes, versions, parent/BOM, repository metadata, and sources/Javadoc classifiers.

With a consumer project:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Gradle:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency domain --configuration runtimeClasspath
~~~

dependencyInsight shows why a version was selected and the dependency path bringing the artifact into the configuration. If the publication includes Gradle Module Metadata, check variant attributes and the artifact file chosen by the consumer; do not inspect only the POM if Gradle consumers use richer metadata.

## 14. Consumer Testing from Published Artifacts

A passing producer build is not enough. You must confirm an independent consumer can resolve and use the artifact from the target repository.

Workflow:

1. Publish to a staging repository or test repository.
2. Create a small consumer project outside the producer workspace.
3. Configure the right repository URL.
4. Declare the dependency using the released coordinates/version.
5. Compile, test, and run smoke tests.
6. Check the dependency tree and checksums of resolved files.
7. Confirm the consumer does not accidentally pull the artifact from a local cache.

Maven dependency:

~~~xml
<dependency>
    <groupId>com.acme.platform</groupId>
    <artifactId>domain</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Run:

~~~bash
./mvnw --batch-mode clean verify
~~~

For a more isolated check, use a separate local repository:

~~~bash
./mvnw -Dmaven.repo.local=/tmp/verify-m2 \
  --batch-mode clean verify
~~~

If the consumer only passes when the producer ran install on the same machine, the test may be pulling the artifact from the local repository instead of the remote repository.

Gradle dependency:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.example.com/releases')
    }
}

dependencies {
    implementation 'com.acme.platform:domain:1.0.0'
}
~~~

Run:

~~~bash
./gradlew --refresh-dependencies clean test
~~~

In audit environments, use a separate Gradle User Home/cache or a clean workspace to test resolution from the target repository.

If the consumer needs to check a specific public class:

~~~bash
javac -cp domain-1.0.0.jar ConsumerCheck.java
java -cp .:domain-1.0.0.jar ConsumerCheck
~~~

On Windows, the classpath separator is a semicolon:

~~~powershell
javac -cp domain-1.0.0.jar ConsumerCheck.java
java -cp ".;domain-1.0.0.jar" ConsumerCheck
~~~

ConsumerCheck must call the actual API provided by the project. This is a template; the class name and source must be replaced with an appropriate consumer fixture.

## 15. Artifact Verification in CI Pipelines

CI should stop immediately when a required check fails.

Example Linux script:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

ARTIFACT="build/libs/domain-1.0.0.jar"
if [ -z "$EXPECTED_ARTIFACT_SHA256" ]; then
  echo "Set trusted EXPECTED_ARTIFACT_SHA256" >&2
  exit 1
fi

test -s "$ARTIFACT"

ACTUAL_SHA256="$(sha256sum "$ARTIFACT" | awk '{print $1}')"
if [ "$ACTUAL_SHA256" != "$EXPECTED_ARTIFACT_SHA256" ]; then
  echo "Artifact checksum mismatch" >&2
  exit 1
fi

echo "CHECKSUM_OK"

unzip -t "$ARTIFACT" >/dev/null
echo "ARCHIVE_OK"

jarsigner -verify -strict -verbose -certs "$ARTIFACT"
echo "JAR_SIGNATURE_OK"

jar --list --file "$ARTIFACT" >/dev/null
echo "JAR_CONTENTS_OK"
~~~

The script assumes the artifact is JAR-signed and CI has EXPECTED_ARTIFACT_SHA256 from a trusted source. If the project uses a detached PGP signature instead of a JAR signature, replace the jarsigner step with GPG verification and verify the publisher fingerprint.

Do not hardcode the expected hash of another release. Each version/build must have its own corresponding digest.

### GitHub Actions

~~~yaml
name: Verify artifact

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'

      - name: Build
        run: ./mvnw --batch-mode clean verify

      - name: Verify dependency checksums
        run: ./mvnw -C --batch-mode verify

      - name: Inspect artifact
        run: |
          test -s target/domain-1.0.0.jar
          unzip -t target/domain-1.0.0.jar
          jar --list --file target/domain-1.0.0.jar
~~~

This example illustrates checking dependency checksums and archive contents. In a real workflow, replace artifact paths/versions for your project; add signature/checksum/provenance steps per your release policy. Run the same verification gates in the real release workflow.

### Maven Strict Checksum

~~~bash
./mvnw -C --batch-mode clean verify
~~~

If the command reports a checksum mismatch, keep the logs, identify the artifact/repository, and investigate the source before updating caches or checksum metadata.

### Gradle Dependency Verification

When a project has committed gradle/verification-metadata.xml, normal builds check the artifacts covered by the metadata. If a checksum/key is missing or contents differ from the metadata, the build reports a verification failure.

Do not disable verification in release jobs just to make the pipeline pass.

## 16. Provenance, SBOM, and Attestation

A Software Bill of Materials (SBOM) lists the components and dependencies contained in an artifact/release. SBOMs are useful for investigating newly disclosed vulnerabilities, tracking licenses, and supporting incident response.

An SBOM does not prove an artifact has not been altered. Bind the SBOM to the exact artifact digest or release identity.

Provenance records the repository, commit, workflow, builder, and related details from which an artifact was created. An attestation can link an artifact digest, source repository/commit, workflow/job, and build identity.

Verify attestations according to platform policy and confirm the subject digest matches the file being used.

A valid attestation does not replace checksum/signature verification. It answers questions about the source and build process; checksums/signatures verify the contents and signer.

An artifact with a valid signature can still contain a vulnerable dependency. An artifact with no known CVEs can still be a tampered file. Release gates typically require integrity, authenticity, dependency/security scans, and consumer tests.

## 17. Checking Releases from a Repository

When verifying a published artifact:

1. Confirm coordinates and release version.
2. Confirm repository URL/namespace.
3. Download the main artifact and metadata.
4. Download the corresponding checksums/signatures.
5. Verify the signature/fingerprint or trusted checksum.
6. Compare SHA-256/SHA-512.
7. Inspect POM/Gradle metadata.
8. Inspect archive contents and manifest.
9. Run consumer tests from the target repository.
10. Store evidence alongside the release record.

Maven Central requires artifacts, POMs, and PGP signatures per repository publishing rules. A published release must not be overwritten with different content. For internal repositories, apply a similar immutable policy to preserve stability for consumers.

### Artifact Staging

If the repository supports staging:

- Publish to staging.
- Re-download the artifact from staging.
- Verify checksums/signatures.
- Run consumer tests.
- Check the POM and attached artifacts.
- Promote to release after all gates pass.

Checking after upload is important because the file in the producer workspace is not necessarily the exact bytes a consumer downloads from the repository.

## 18. Common Errors and Troubleshooting

### SHA-256 Mismatch

**Cause:** wrong file/version downloaded, corrupted artifact, mirror returning different bytes, altered file, or incorrect expected checksum.

**Resolution:** stop using the file; confirm coordinates/URL; recompute digest; obtain checksum from an independent source; re-download from a trusted repository; do not edit the expected checksum just to make the pipeline pass.

### Sidecar Checksum Matches but Publisher Unknown

**Cause:** the checksum was downloaded alongside the artifact from the same repository, so both could have been altered together.

**Resolution:** verify the PGP/JAR signature or obtain a trusted checksum via an independent channel; compare the signer fingerprint.

### JAR Unsigned

**Cause:** the publisher did not sign the JAR with jarsigner, or signature files are missing from the archive.

**Resolution:** check the project/repository policy. If a JAR signature is required, reject the unsigned artifact. If the project uses detached PGP signatures, verify the .asc file instead of expecting JAR signature entries.

### jarsigner Reports Signature Verification Failed

**Cause:** an entry was modified after signing, signature block is corrupted, digest mismatch, or algorithm is disabled.

**Resolution:** re-download the official artifact; check SHA-256; verify signature files and individual entries; do not modify a signed JAR.

### jar verified but Signer Untrusted

**Cause:** the cryptographic signature is valid, but the certificate is self-signed, the chain is unvalidated, or the key does not belong to the expected publisher.

**Resolution:** check -verbose -certs; compare the fingerprint against an independent source; use a truststore/keystore containing verified certificates; enable -strict.

### Expired Certificate or Timestamp Warning

**Cause:** certificate expired, TSA chain error, or invalid timestamp.

**Resolution:** inspect warning details and the certificate chain; check the timestamp token; confirm signing-time policy. Do not automatically ignore severe warnings.

### PGP Good signature but Key Untrusted

**Cause:** the signature matches the key, but the fingerprint has not been verified or the key could be spoofed.

**Resolution:** obtain the public key from an official source; compare the full fingerprint via an independent channel; only then trust the signature.

### Maven Reports Checksum Mismatch

**Cause:** downloaded artifact differs from the repository-published checksum, unsynced mirror, stale cache, or altered artifact.

**Resolution:** keep logs and coordinates; check repository origin/mirror; re-download from a trusted source; do not use -c to hide errors in release gates.

### Gradle Dependency Verification Failed

**Cause:** missing checksum, artifact bytes differ from metadata, PGP signature/key changed, or new dependency not yet reviewed.

**Resolution:** read the exact artifact/configuration/repository in the error; verify the upstream release; review the new checksum/key; update metadata in a controlled manner. Do not run the metadata generation command and commit immediately without review.

### JAR Opens Cleanly but Missing Classes/Resources

**Cause:** wrong classifier published, wrong build variant, packaging task omitted output, or artifact is not the expected version.

**Resolution:** list the JAR; inspect POM/Gradle metadata; compare with build output artifact; run consumer tests.

### Consumer Compiles but Fails at Runtime

**Cause:** missing transitive dependency, wrong dependency scope/variant, class version too new, service provider/resource not packaged, or JPMS module fails to resolve.

**Resolution:** inspect dependency tree/runtime classpath; check class major version; check manifest/services/module descriptor; run tests on the exact target runtime.

### POM Is Correct but JAR Is Wrong

**Cause:** wrong file uploaded manually, publication points to wrong artifact, repository overwrite, or cache holding a different build.

**Resolution:** download the file from the repository with a clean cache; compute SHA-256; compare with build output and release manifest; check publication task/artifact mapping.

### Only One Platform Fails

**Cause:** wrong classifier/variant for OS/architecture, missing native library, or different bytecode/runtime.

**Resolution:** check variant selection, artifact classifier, architecture, and native dependencies; test on every supported platform.

### Artifact Hash Changes After Signing

**Cause:** the file was edited, repacked, or metadata was added after signing.

**Resolution:** identify which step modified the file; re-sign the final artifact; update checksums/signatures/attestations; do not reuse old signatures.

## 19. Artifact Verification Report Template

| Field | Value to Record |
|---|---|
| Artifact identity | groupId, artifactId, version, classifier, extension |
| Repository | URL/namespace with credentials redacted |
| File | Name, size, path |
| SHA-256 | Digest computed from received file |
| Expected digest | Source and reference value |
| Checksum result | PASS/FAIL |
| Signature type | JAR, PGP, or none |
| Signer | Certificate/key fingerprint |
| Signature result | PASS/FAIL and warnings |
| Structure | JAR integrity, manifest, classes/resources |
| Compatibility | Java version, API, module/dependency checks |
| Consumer test | Build/test result from repository |
| Provenance | Attestation subject digest/source/workflow |
| Decision | ACCEPT/REJECT and reason |

Do not mark PASS if only a checksum downloaded from the same source is present without a policy-based trust decision. Clearly state the verification level actually achieved.

## 20. Checklist Before Accepting an Artifact

### Identity and Source

- [ ] Coordinates, version, classifier, and extension are correct.
- [ ] Repository URL matches an approved source.
- [ ] Not accidentally pulling a snapshot or old version.
- [ ] POM/Gradle metadata matches the artifact.
- [ ] Sensitive credentials/URLs are redacted from logs.

### Integrity and Authenticity

- [ ] SHA-256 or SHA-512 is computed from the actual file.
- [ ] Expected digest comes from a trusted source.
- [ ] JAR signature or PGP signature is verified when required by policy.
- [ ] Signer fingerprint is independently verified.
- [ ] Certificate/algorithm warnings are addressed.
- [ ] Artifact was not modified after signing.

### Contents and Compatibility

- [ ] Archive opens and lists cleanly.
- [ ] Manifest and version metadata are correct.
- [ ] Expected classes/resources are present.
- [ ] No secrets or unintended files.
- [ ] Class file version matches the target runtime.
- [ ] JPMS descriptor/dependencies are correct if used.
- [ ] Consumer compile/test from the target repository succeeds.

### Release Evidence

- [ ] Dependency verification metadata is reviewed.
- [ ] SBOM/provenance is bound to the exact artifact digest.
- [ ] Staging artifact is re-downloaded and verified.
- [ ] Report records digest, signer, source, and results.
- [ ] Release repository enforces an immutable version policy.
- [ ] Clear ACCEPT/REJECT decision is recorded.

## 21. Standard Artifact Verification Workflow

1. Identify exact coordinates, file, and repository.
2. Download the artifact and metadata into a clean workspace.
3. Compute SHA-256/SHA-512.
4. Compare with a trusted checksum or verify the signature.
5. Confirm the signer fingerprint.
6. Inspect archive, manifest, and contents.
7. Check class version, API, modules, and dependencies.
8. Resolve the artifact in an independent consumer project.
9. Run compile, test, and smoke tests on the target runtime.
10. Verify SBOM/provenance if required by release policy.
11. Save the verification report.
12. Accept the artifact only when all required gates pass.

When a step fails, preserve the artifact and logs for investigation. Do not alter the expected checksum, disable strict mode, or drop signature requirements just to keep the pipeline running.

## 22. Official References

- [The jarsigner Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html) — verifying JAR signatures, certificates, keystores, verbose output, strict mode, and timestamps.
- [Jarsigner — Dev.java](https://dev.java/learn/jvm/tool/security/jarsigner/) — examples of signing and verifying JARs, displaying signer certificates.
- [Gradle Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html) — checksums, PGP signatures, transitive dependencies, and verification metadata.
- [Gradle Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html) — repository trust, centralized declarations, and artifact verification.
- [Maven CLI Options Reference](https://maven.apache.org/ref/3.9.16/maven-embedder/cli.html) — -C/--strict-checksums and -c/--lax-checksums.
- [Maven Resolver: About Checksums](https://maven.apache.org/components/resolver-archives/resolver-2.0.24/about-checksums.html) — transport checksums, trust limitations, and SHA-256/SHA-512.
- [Maven Resolver: Expected Checksums](https://maven.apache.org/resolver/expected-checksums.html) — trusted checksum sources and summary checksum files.
- [Guide to Uploading Artifacts to Maven Central](https://maven.apache.org/repository/guide-central-repository-upload.html) — release artifacts, POMs, PGP signatures, and immutable release policy.
- [Download Apache Maven](https://maven.apache.org/download.cgi) — SHA-512 checksums and .asc signatures of Maven distributions.
- [The javap Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html) — reading class file metadata and bytecode.
- [The jdeps Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html) — analyzing dependencies of Java classes and modules.

Artifact verification must check the identity, bytes, signer, structure, and usability of the received file. Checksums detect content differences; signatures verify the signing key; provenance links the artifact to its source/workflow; consumer tests confirm the file actually works in the target environment. Combine these layers according to your release policy and retain evidence so others can audit the artifact acceptance decision.
