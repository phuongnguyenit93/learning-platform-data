# Attaching Checksums, Signatures, and Traceability Metadata to Artifacts

## 1. Objective: Proving the Right File, Right Publisher, and Right Build Process

When releasing a Spring Boot application, recipients need to answer three distinct questions:

1. **Was the artifact modified?** Compare the cryptographic checksum (e.g., SHA-256) of the received file against a digest published through a trusted channel.
2. **Who signed/published the artifact?** Verify the digital signature using a public key or certificate chain, then check whether the signer identity matches the trust policy.
3. **How was the artifact built?** Inspect provenance to see the source repository/commit, build definition, builder identity, dependencies, and output digest; cross-check the SBOM to know which components reside inside the product.

These three mechanisms complement one another:

- **Checksum** is a fingerprint of bytes. It detects whether a file differs from a reference digest, yet a checksum by itself does not prove who created the file.
- **Digital signature** authenticates a signature bound to a trusted key/identity and protects signed content against undetected tampering.
- **Build provenance** describes inputs and the process used to produce the output. Provenance must be emitted by a trusted builder/CI and signed/attested so recipients can verify its origin.

Spring Boot release example:

~~~text
Git tag + commit
       │
       ▼
CI: clean test + bootJar / mvn package
       │
       ▼
Executable JAR ── SHA-256 checksum
       │           └─ signature / verification bundle
       ▼
Container image ── image digest
       │           ├─ Cosign image signature
       │           ├─ SLSA provenance attestation
       │           └─ SBOM attestation
       ▼
Publish immutable artifact/image
       │
       ▼
Consumer verifies digest + signer + provenance policy
       │
       ▼
Deploy exact verified image digest
~~~

After this lesson, you will be able to compute SHA-256 checksums for Spring Boot JARs, sign JARs or sign raw files with Sigstore Cosign, sign OCI images by digest, attach SLSA provenance/SBOMs, verify signatures, and apply these steps in Gradle/Maven CI pipelines.

**Scope:** examples use Java 17 and Spring Boot 3.3.13 to illustrate artifact building. Cosign, Sigstore, SLSA, and build tools must be pinned/verified to versions used by your organization; commands below describe workflows rather than claiming a specific tool release is the latest.

## 2. Distinguishing Checksums, Signatures, Provenance, and SBOMs

| Component | Question answered | What does it protect? | What it does not prove alone |
| --- | --- | --- | --- |
| SHA-256 checksum | Do current bytes match the reference digest? | Integrity / change detection | Who built the file, or whether the file is safe |
| Digital signature | Which key/identity signed this content? | Authenticity + integrity of signed payload | Good source code, clean build, or absence of malware |
| Build provenance | Which source, builder, parameters, and dependencies produced the output? | Traceability / auditability | That the artifact has no vulnerabilities |
| SBOM | Which components does the artifact contain? | Inventory and dependency analysis | Who built the artifact |
| Reproducible build | Can identical bytes be rebuilt from equivalent inputs/build process? | Reproducibility and independent verification | That the publisher or source is trustworthy |

### 2.1. A Checksum Is Meaningful Only When the Reference Digest Is Trusted

Suppose the publisher sends two files:

~~~text
app.jar
app.jar.sha256
~~~

If an attacker replaces both the JAR and the checksum file on the same unprotected server, the recipient will still compute a matching checksum. Therefore, obtain the digest from an independent trusted source, or sign the checksum manifest with a digital signature that has a clear trust chain.

Checksums are very useful for catching transfer errors, corrupted files, wrong versions, or unintended edits. However, they do not replace signatures.

### 2.2. Signatures Require a Trust Policy

A file having a valid signature means the signature matches the corresponding public key/certificate. The verifier must still ask:

- Does that public key belong to an authorized releasing organization/workflow?
- Does the certificate have a valid chain and identity?
- Do the OIDC issuer and identity match the right repository/workflow/ref?
- Has the signing key been compromised/revoked, or has policy changed?
- Is the signature bound to the exact digest of the artifact/image being received?

Never accept a signature merely because the verify command returns success against an arbitrary public key supplied by the artifact source itself.

### 2.3. Provenance Differs from build-info.properties

Spring Boot build-info or manifests may record version, build time, and Git commit. Those values are helpful operationally, yet they are usually written into the artifact by the build script itself. They do not prove the builder actually executed that source commit.

SLSA/in-toto provenance describes the build definition and execution, builder identity, and output subject digest. When generated by a trusted build platform and signed/attested, consumers can verify origin claims against policy.

### 2.4. SBOM Differs from Provenance

An SBOM (Software Bill of Materials) lists components/dependencies, versions, licenses, or package metadata. Provenance describes **how the product was built**. An image with a complete SBOM could still have been built from untrusted sources; valid provenance does not automatically enumerate every library unless the builder generates an SBOM.

Good releases typically publish both, bound to the same image digest.

## 3. Generating SHA-256 Checksums for Spring Boot Artifacts

Suppose Gradle built the executable Boot JAR:

~~~bash
./gradlew clean test bootJar
~~~

If the project configures archive output name `app.jar`, the example path is:

~~~text
build/libs/app.jar
~~~

The Maven equivalent can be:

~~~bash
mvn clean verify
~~~

With `<finalName>app</finalName>` in the POM, the example artifact is at:

~~~text
target/app.jar
~~~

Exact names/paths depend on project configuration. Hash and sign the **exact final executable Boot JAR**, not `-plain.jar` or an intermediate pre-repackage file.

### 3.1. Linux/macOS: sha256sum

Create sidecar:

~~~bash
sha256sum build/libs/app.jar > app.jar.sha256
~~~

Verify:

~~~bash
sha256sum --check app.jar.sha256
~~~

If the sidecar records the right filename and bytes are unchanged, output looks like:

~~~text
build/libs/app.jar: OK
~~~

The displayed path depends on the path recorded in the sidecar. If moving the artifact to another directory, ensure the sidecar references the right file or regenerate the sidecar in the release directory.

SHA-512 can be computed similarly:

~~~bash
sha512sum build/libs/app.jar > app.jar.sha512
sha512sum --check app.jar.sha512
~~~

SHA-256 and SHA-512 are suitable choices for modern digest integrity. Never use MD5 or SHA-1 to protect new artifacts because both suffer from collision weaknesses.

### 3.2. Windows PowerShell

~~~powershell
Get-FileHash .\build\libs\app.jar -Algorithm SHA256
~~~

PowerShell prints `Algorithm`, `Hash`, and `Path`. Compare `Hash` against the digest retrieved from the release manifest/trusted channel.

If a sidecar is saved in text format with the digest as the first token and filename as the remainder:

~~~powershell
$actual = (Get-FileHash .\build\libs\app.jar -Algorithm SHA256).Hash.ToLowerInvariant()
$expected = (Get-Content .\app.jar.sha256 -Raw).Trim().Split()[0].ToLowerInvariant()

if ($actual -ne $expected) {
    throw "SHA-256 mismatch"
}

"SHA-256 OK"
~~~

This snippet assumes the sidecar holds a text checksum whose first token is the digest. If the repository uses JSON or another format, parse according to that format's schema instead of `Split()[0]`.

### 3.3. Never Fabricate Checksums

SHA-256 depends on every single byte of the artifact. You cannot guess a digest from filename, version, or source code alone. Compute the digest after the artifact is completely packaged, then store the real value in the manifest/release metadata.

## 4. Java 17: Program to Compute SHA-256 for a File

This standalone example uses Java SE without needing Spring Boot, Gradle, or Maven. It reads the file via a buffer so the entire JAR does not need to be loaded into RAM.

Create `ArtifactSha256.java`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class ArtifactSha256 {

    private ArtifactSha256() {
    }

    public static void main(String[] args)
            throws IOException, NoSuchAlgorithmException {

        if (args.length != 1) {
            System.err.println("Usage: java ArtifactSha256 <file>");
            System.exit(2);
        }

        Path file = Path.of(args[0]);
        MessageDigest digest = MessageDigest.getInstance("SHA-256");

        try (InputStream input = Files.newInputStream(file)) {
            byte[] buffer = new byte[8192];
            int count;

            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        String hex = HexFormat.of().formatHex(digest.digest());
        System.out.println("SHA-256=" + hex);
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac ArtifactSha256.java
java ArtifactSha256 build/libs/app.jar
~~~

Output takes the form:

~~~text
SHA-256=<64 hex characters depending on actual bytes of app.jar>
~~~

`<64 hex characters...>` describes the output format, not a copyable checksum. The real result changes whenever the file changes.

### 4.1. Why Use MessageDigest and HexFormat?

- `MessageDigest.getInstance("SHA-256")` obtains the SHA-256 hash implementation from Java security providers.
- `update(buffer, 0, count)` feeds chunks into the digest, supporting large files.
- `digest()` finalizes and returns 32 bytes (256 bits).
- `HexFormat.of().formatHex(...)` formats those 32 bytes as 64 hexadecimal characters.
- `try-with-resources` closes the InputStream even if reading fails.

This program only **computes a digest**. It does not know which reference digest is trustworthy; verification must still compare against a published/signed digest from a trusted source.

## 5. Checksum Workflow for Releases

A release directory may contain:

~~~text
release/
├── app.jar
├── app.jar.sha256
├── app.jar.sigstore.json
├── sbom.spdx.json
└── release-notes.txt
~~~

Meaning:

- `app.jar`: executable artifact.
- `app.jar.sha256`: digest sidecar for change detection.
- `app.jar.sigstore.json`: Sigstore bundle containing signature and verification metadata for the blob.
- `sbom.spdx.json`: component inventory of the artifact, if generated by the pipeline.
- Provenance can be stored as an attestation in an OCI registry, release store, or controlled artifact metadata system.

**Order matters:** if using `jarsigner` to modify the JAR, compute the checksum and sign with Cosign blob **after JAR signing completes**. Modifying/repackaging the JAR after generating a checksum or signature invalidates the old digest/signature.

Cosign `sign-blob` creates a detached bundle without altering JAR contents; the JAR's checksum does not change when the bundle is created. Recipients must receive both the JAR and the bundle while also verifying the signer's identity.

## 6. Digital Signatures: Private Key, Public Key, and Trust

Digital signatures use a key pair:

- **Private key** creates the signature. Only the authorized signer or signing service may use this key.
- **Public key** verifies the signature. Consumers can obtain the public key through an independent trust channel.
- **Certificate** can bind a public key to an identity/organization via a CA.
- **Trust policy** determines which certificates/keys/identities are allowed to release artifacts.

If a signed file changes by even one byte, verification must fail (if that byte is within the signed payload). However, a valid signature does not mean the software has no bugs or no malware.

### 6.1. Two Key Management Models

| Model | How it works | Pros | Risks/conditions |
| --- | --- | --- | --- |
| Key-based | Uses long-lived key pair, typically in KMS/HSM/secure key store | Clear key trust control, works in private networks | Must protect, back up, rotate, and revoke keys |
| Keyless (Sigstore) | Uses OIDC identity, ephemeral keys, and short-lived certificates | Reduces holding long-lived private keys | Must verify exact OIDC issuer, identity, and workflow policy |

Never store private signing keys in Git repositories, Docker images, JARs, build logs, or artifact outputs. Never pass passwords/secrets as command-line arguments that may be captured in process lists/logs. CI should use workload identity, KMS/HSM, or an organization-approved secret manager.

## 7. Signing JARs with JDK jarsigner

The JDK provides `jarsigner` to sign and verify JARs. It updates the manifest and adds signature files inside `META-INF`, typically `.SF` and a signature block `.RSA`, `.DSA`, or `.EC`.

### 7.1. Preparing a Certificate/Keystore

In a lab you can generate a PKCS12 keystore and test certificate:

~~~bash
keytool -genkeypair \
  -alias release-signing \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -storetype PKCS12 \
  -keystore release.p12
~~~

The command prompts for passwords and certificate details. Self-signed certificates are fine for learning syntax, **not for establishing trust with recipients**. Production requires an organization-approved certificate chain/trust anchor or keys managed in an HSM/KMS.

### 7.2. Signing a JAR

~~~bash
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -signedjar app-signed.jar \
  build/libs/app.jar \
  release-signing
~~~

If no password is passed on the command line, the tool may prompt interactively. In CI, use a secure secret/key provider supported by the JDK and your organization; never hardcode passwords in scripts.

### 7.3. Verifying a Signed JAR

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

Read all warnings. `-strict` turns severe warnings into errors per jarsigner rules. Cryptographic signature success does not mean a self-signed certificate is trusted by recipients; verify the chain, signer identity, validity, timestamp, and policy.

### 7.4. What Does JAR Signing Sign?

JAR signing writes digests for entries in the archive and signs the signature file. It verifies that signed entries were not altered and the signature was created by the private key matching the certificate. This is useful when distribution systems/loaders support JAR signatures.

However, JAR signing differs from signing the entire file blob:

- `jarsigner` verifies entries and manifest per the JAR signing specification.
- Cosign `sign-blob` signs the payload of the entire artifact file as a blob and keeps the bundle outside the file.
- JAR signatures do not describe source commit, build runner, or dependency graph.
- JAR signatures do not sign OCI image manifests/layers.

With Spring Boot executable JARs, complete Gradle `bootJar` or Maven `repackage` before signing. Never modify/repackage a JAR after signing; run smoke tests on **the exact signed file** and verify with the JDK/runtime used by the target environment. When the goal is verifying byte-level integrity of the whole release file, SHA-256 and Cosign blob signatures can also be used.

## 8. Sigstore Cosign: Signing a JAR File as a Blob

Cosign can sign regular files, not just container images. With keyless signing, Cosign uses OpenID Connect to authenticate identity; Sigstore Fulcio issues a short-lived certificate bound to an ephemeral public key, and Rekor records the event in a transparency log. The bundle lets consumers keep the signature, certificate, and proof needed for verification.

### 8.1. Keyless Blob Signing

Once Cosign is installed and OIDC is authenticated:

~~~bash
cosign sign-blob --bundle app.jar.sigstore.json build/libs/app.jar
~~~

In interactive environments, Cosign may prompt for OIDC login. In CI, workload identity/OIDC provider must be configured properly. `app.jar.sigstore.json` is the verification bundle, not a modified JAR file.

The Sigstore transparency log can create a public record of the digest and signing identity. Before signing internal/sensitive artifacts, review your organization's metadata disclosure policy.

### 8.2. Verifying a Blob by Permitted Identity

~~~bash
cosign verify-blob \
  --bundle app.jar.sigstore.json \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  build/libs/app.jar
~~~

`SIGNER_IDENTITY` and `OIDC_ISSUER` must come from real release policy, such as the specific CI workflow identity and matching issuer. Never set broad wildcards like `.*` in production policy when the goal is accepting only an approved release workflow.

If the bundle is missing, the file was altered, or identity/issuer do not match, verification must fail. Never bypass failures by disabling claim checking in release gates.

### 8.3. Key-Based Blob Signing

When using a self-managed key pair:

~~~bash
cosign generate-key-pair
cosign sign-blob \
  --key cosign.key \
  --bundle app.jar.sigstore.json \
  build/libs/app.jar
~~~

Consumers verify using the public key distributed through a trusted channel:

~~~bash
cosign verify-blob \
  --key cosign.pub \
  --bundle app.jar.sigstore.json \
  build/libs/app.jar
~~~

`cosign.key` must be protected and never published. For production, prefer KMS/HSM or a secret manager over long-lived private key files on CI workers. When using key-based signing, manage public key rotation and clear key revocation workflows.

## 9. Signing OCI Container Images by Digest

When an application is packaged as an OCI image, sign the **image digest** rather than relying solely on mutable tags like `:latest` or `:1.2.3`.

Tags can be repointed by the registry to another image. Digests identify specific manifest contents. Consumers should pull/verify/deploy the exact reference:

~~~text
registry.example.com/team/jvm-compat-demo@sha256:<actual-digest>
~~~

The string above illustrates the format; replace it with the real digest returned by the registry. Never invent digests.

### 9.1. Push Image Then Resolve Digest

Example release tag:

~~~bash
IMAGE_TAG=registry.example.com/team/jvm-compat-demo:1.0.0
~~~

After CI pushes the image, use an appropriate registry tool (e.g., `crane`) to resolve the digest:

~~~bash
crane digest "$IMAGE_TAG"
~~~

Construct the digest-based image reference from the real output. Shell example:

~~~bash
IMAGE_DIGEST="$(crane digest "$IMAGE_TAG")"
IMAGE_REF="registry.example.com/team/jvm-compat-demo@$IMAGE_DIGEST"
~~~

Never sign a tag before knowing the final artifact was pushed and its digest is fixed. If the registry or tool returns a different digest, inspect the manifest/architecture/index and select the exact image reference to release.

### 9.2. Keyless Image Signing with Cosign

~~~bash
cosign sign "$IMAGE_REF"
~~~

Cosign uses the OIDC identity flow in supported environments and stores the signature linked to the image digest in the registry using OCI referrers/registry support as appropriate.

### 9.3. Verifying an Image Signature

~~~bash
cosign verify "$IMAGE_REF" \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER"
~~~

Cosign verifies the signature, certificate identity/issuer, and digest claims. Consumers still need policy to confirm the right workflow, repository, tag/ref, and authorized releasing organization. An image signed by an unapproved account does not become a trusted image.

### 9.4. Key-Based Image Signing

~~~bash
cosign sign --key cosign.key "$IMAGE_REF"
cosign verify --key cosign.pub "$IMAGE_REF"
~~~

With a registry, the signature is stored as an artifact/referrer if the registry supports it. If using an older registry or one with limited OCI referrers support, check Cosign and registry compatibility guidance; do not assume all registries store signatures identically.

**Do not:** build a new image overwriting the same tag while reusing the signature of the old digest. Resolve the digest, sign the new digest, verify the new digest, and deploy that exact digest.

## 10. Provenance with SLSA/in-toto

SLSA provenance is an attestation describing **where an artifact was built and by what process**. In SLSA provenance v1, key parts include:

- `subject` in the in-toto Statement: the output artifact, identified by digest.
- `predicateType`: standard URI `https://slsa.dev/provenance/v1`.
- `buildDefinition`: build type, external parameters, and resolved dependencies.
- `runDetails`: builder identity, run metadata, and related details.
- `resolvedDependencies`: artifacts required for the build, if collected by the builder.

Provenance answers questions such as: which repository and commit built this image, by which builder/workflow, with what parameters/dependencies, and producing which output digest?

### 10.1. Illustrative Predicate

This is a **structural example to understand the fields**, not real provenance and not proof of any SLSA level. Values must be recorded by a trusted build platform:

~~~json
{
  "buildDefinition": {
    "buildType": "https://ci.example.org/buildtypes/gradle-spring-boot/v1",
    "externalParameters": {
      "repository": "https://git.example.org/team/jvm-compat-demo",
      "gitRef": "refs/tags/v1.0.0",
      "gitCommit": "FULL_COMMIT_SHA_FROM_CI",
      "entryPoint": "./gradlew clean test bootJar"
    },
    "resolvedDependencies": []
  },
  "runDetails": {
    "builder": {
      "id": "https://ci.example.org/builders/release-v1"
    },
    "metadata": {
      "invocationId": "ci://jvm-compat-demo/release/12345",
      "startedOn": "2026-11-09T02:00:00Z",
      "finishedOn": "2026-11-09T02:04:00Z"
    }
  }
}
~~~

In a real release, `gitCommit` must be the real commit SHA, `builder.id` must identify an approved builder, invocation ID must point to an auditable run, timestamps must come from CI, and resolved dependencies must be complete per the builder's claimed assurance level. Never use the placeholder strings above as release claims.

### 10.2. Attesting SLSA Provenance to an OCI Image

Once you have the predicate generated by the build platform, Cosign can attach and sign the attestation:

~~~bash
cosign attest \
  --type slsaprovenance1 \
  --predicate provenance.json \
  "$IMAGE_REF"
~~~

`slsaprovenance1` is Cosign's type alias for SLSA provenance v1. Cosign creates an in-toto statement binding the subject to the specified image, signs the attestation, and stores it in the registry per supported mechanism.

**Trust warning:** Cosign signs whatever data is passed in; it does not verify that the provenance contents are truthful. If a developer writes JSON by hand and signs it with a personal account, that only proves that person signed that claim. For provenance to have supply-chain value, source it from a trusted CI/build platform, verify builder identity, and prevent build scripts from forging platform-controlled fields.

### 10.3. Verifying Attestation and Signer Identity

~~~bash
cosign verify-attestation \
  --type slsaprovenance1 \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  "$IMAGE_REF"
~~~

This checks the attestation signature/identity/type for the image. Next, the consumer must inspect the payload and enforce policy on:

- Does the subject digest match the exact image about to be deployed?
- Are the source repository and commit authorized?
- Is the Git ref an approved release tag/branch?
- Does the builder ID belong to a trusted CI platform?
- Do build type/parameters match the release workflow?
- Does the invocation ID exist and correspond to CI logs/records?
- Are dependencies/builder inputs within policy?

Verifying only the cryptographic signature without checking critical claims can accept a validly signed provenance pointing to the wrong repository or workflow.

## 11. SBOM: Inventory Accompanying the Artifact

An SBOM shows which components reside in the artifact/image, for example:

- Spring Boot libraries, embedded server, and transitive dependencies.
- Java runtime, OS packages, and native libraries inside the OCI image.
- Versions, package identifiers, licenses, and dependency relationships in a supported format.

Common formats include SPDX and CycloneDX. Example generating SPDX JSON for an image using Syft (when installed and version-pinned):

~~~bash
syft "$IMAGE_REF" -o spdx-json > sbom.spdx.json
~~~

Attach the SBOM as an attestation:

~~~bash
cosign attest \
  --type spdxjson \
  --predicate sbom.spdx.json \
  "$IMAGE_REF"
~~~

Verify the attestation with the matching type:

~~~bash
cosign verify-attestation \
  --type spdxjson \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  "$IMAGE_REF"
~~~

Ensure the SBOM is generated from **the exact image digest being signed**, not from the source tree prior to image assembly. SBOMs help scanners look up CVEs/licenses; they do not prove all components are safe or provenance is valid.

## 12. Gradle Dependency Verification: Protecting Input Libraries

Gradle provides dependency verification via:

~~~text
gradle/verification-metadata.xml
~~~

This file lets Gradle verify checksums and/or PGP signatures of resolved dependencies/plugins. This **checks build input artifacts**, not signing the newly built application JAR.

Generate baseline metadata (after resolving from inspected repositories):

~~~bash
./gradlew --write-verification-metadata sha256
~~~

When libraries have PGP signatures and the team wants to store both checksum and signature metadata:

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

After generating:

1. Review the entire `verification-metadata.xml`.
2. Verify checksums/signatures/keys of critical dependencies against independent official sources.
3. Commit the metadata file alongside build configuration.
4. When dependency versions change, review the diff and update intentionally.
5. Ensure CI builds fail if any artifact does not match metadata.

Gradle supports SHA-256/SHA-512 for modern checksums; never use MD5/SHA-1 as new trust anchors. PGP signatures are only meaningful when keys are trusted. Bootstrapping metadata from a live repository has a caveat: if the repository is already compromised, checksums from malicious artifacts could be written into the baseline. Review is mandatory.

Gradle dependency verification does not cover local artifacts built during the build and has limitations with changing dependencies such as SNAPSHOTs. Thus, **separate checksums/signatures/provenance for the released product** are still required.

## 13. Maven: Repository Checksums, Signatures, and Artifact Releases

Maven repositories store JARs, POMs, metadata, and optionally checksum/signature files. The Maven Deploy Plugin handles uploading artifacts and related files per the repository deployment workflow. However:

- Sidecar checksums from the same repository help detect corruption/transit errors, yet if both JAR and checksum are replaced, they do not authenticate the publisher.
- Checksum algorithms/policies depend on the repository manager and configuration; do not assume `.sha1` or `.md5` files provide modern security.
- Detached PGP `.asc` signatures must be verified against a confirmed public key/trust policy.
- JAR signing with `jarsigner` is a separate mechanism signing entries inside the archive.
- Cosign blob signatures can sign entire JAR bytes and keep the bundle externally.

A Maven release workflow might run:

~~~bash
mvn clean verify
mvn package
sha256sum target/app.jar > app.jar.sha256
~~~

Then sign the final file with `jarsigner` or Cosign, and publish the artifact, checksum, and signature/bundle to the repository/release storage. Use an organization-configured release profile/signing plugin; never hardcode private keys/passwords in the POM.

For dependency inputs, Maven Resolver/repository checksum policies and signature verification must be configured explicitly. Do not mistake repository-generated sidecar checksums for a digital signature authenticating publisher identity.

## 14. An End-to-End Workflow for Spring Boot

Suppose CI builds:

- Gradle: `build/libs/app.jar` from task `bootJar`.
- Maven: `target/app.jar` after goal `repackage`.
- Container image: `registry.example.com/team/app:1.0.0`.

### 14.1. Build and Test

Gradle:

~~~bash
./gradlew clean test bootJar
~~~

Maven:

~~~bash
mvn clean verify
~~~

Proceed only after the test gate passes and the exact executable file is built. Do not sign intermediate artifacts or plain JARs.

### 14.2. Inspect Artifact and Generate Checksum

~~~bash
sha256sum build/libs/app.jar > app.jar.sha256
sha256sum --check app.jar.sha256
~~~

Store the checksum manifest with the release and include the digest in release metadata/provenance. If the artifact is later signed with jarsigner, generate a new checksum after JAR signing finishes.

### 14.3. Sign the JAR

One of two options:

- `jarsigner` when consumers require JAR entry signatures and have matching trust/certificate policies.
- Cosign `sign-blob` when signing the entire file bytes via Sigstore bundle/keyless or key/KMS.

No need to automatically run both if policy requires only one; if using both, define purpose and ordering clearly.

### 14.4. Build Image and Obtain Digest

Build/push the image via CI. After push, resolve the immutable digest from the registry, e.g., using `crane digest`. Record both the release tag and digest:

~~~text
tag:    registry.example.com/team/app:1.0.0
digest: registry.example.com/team/app@sha256:<actual-digest>
~~~

Sign and attest by the digest reference, not solely by tag.

### 14.5. Sign Image and Attach Provenance/SBOM

~~~bash
cosign sign "$IMAGE_REF"

cosign attest \
  --type slsaprovenance1 \
  --predicate provenance.json \
  "$IMAGE_REF"

cosign attest \
  --type spdxjson \
  --predicate sbom.spdx.json \
  "$IMAGE_REF"
~~~

In CI, the OIDC identity must belong to an authorized release workflow. Provenance and SBOM must be generated from the exact same build/digest; never reuse attestations from another image simply because the tag matches.

### 14.6. Verify Before Publish/Deploy

~~~bash
cosign verify "$IMAGE_REF" \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER"

cosign verify-attestation \
  --type slsaprovenance1 \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  "$IMAGE_REF"

cosign verify-attestation \
  --type spdxjson \
  --certificate-identity "$SIGNER_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  "$IMAGE_REF"
~~~

After verification, evaluate claims against policy: repo, commit, ref, builder, invocation, and subject digest. Deploy **the exact verified digest**, rather than re-resolving the tag and accidentally pulling another image.

## 15. Reproducible Builds and Traceability

A reproducible build is the ability to rebuild an artifact with identical bytes from the same source, build instructions, and defined environment. This enables independent comparison of artifacts against release candidates.

Maven offers `project.build.outputTimestamp` and plugins supporting reproducible archives. Gradle offers archive tasks with reproducible timestamp/file ordering settings. However:

- Reproducibility alone does not prove the source is trustworthy.
- Non-reproducibility alone does not prove an attack occurred; timestamps, absolute paths, generated files, and tool versions can alter outputs.
- Build-info/version/Git SHA inside a JAR do not replace signed provenance.
- Signatures bind strictly to the exact built artifact; if a rebuild produces different bytes, the digest/signature will differ too.

For solid traceability, record:

- Source repository URL, commit SHA, and release tag.
- Gradle wrapper/Maven/plugin versions and Java toolchain.
- Dependency locks/verification metadata and resolved dependency set.
- Builder image/CI workflow identity/version.
- Build invocation ID, timestamps, and external parameters.
- Output JAR digest, OCI image digest, and architecture.
- Signer identity, certificate issuer, signature bundle/transparency log evidence.
- SBOM, scan results, and release approval.
- Actual digest deployed to each environment.

Never place secrets, private keys, repository passwords, access tokens, or unnecessary personal data in provenance/SBOM/build-info. Public attestations can expose source URLs, workflow identities, commit SHAs, and build metadata.

## 16. Verification Rules and Failing Closed

A release consumer should reject an artifact if any mandatory condition fails:

1. Checksum does not match the reference digest.
2. Signature is invalid or signer is not in the trust policy.
3. OIDC issuer/identity does not match an approved release workflow.
4. Image signature is attached to a different digest than the pulled image.
5. Provenance lacks subject/output digest or subject does not match the artifact.
6. Source repository, commit, tag, or builder ID is unauthorized.
7. Provenance was signed by an identity lacking release authorization.
8. Mandatory SBOM/scan policy is missing or failed.
9. Attestation cannot be parsed or transparency evidence fails policy verification.

Never downgrade policy to "warn only" in production just to let a build proceed. When metadata is missing due to a release system failure, halt publishing/deployment, investigate, and regenerate the artifact/attestation properly.

### 16.1. Verifying a Signature Differs from Verifying Policy

`cosign verify` checks the signature and image claims. `cosign verify-attestation` checks the attestation signature/claims. Yet policy must also inspect **predicate contents**: is the source repo right, is the builder trusted, does commit/ref match a real release? CUE/Rego policies with Cosign or cluster admission controllers can enforce this.

### 16.2. Never Verify Using a Public Key Supplied by the Artifact Itself

A public key/certificate inside a bundle enables mathematical signature verification, but trust must come from external policy: approved issuer/identity, trusted root, pinned public key/KMS identity, or releasing organization. If an attacker generates their own key and signs their artifact, verifying with the attacker-provided public key will pass mathematically without making the artifact trustworthy.

## 17. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| SHA-256 mismatch | File altered, corrupted download, wrong version/path | Fetch artifact/digest from trusted source; never edit sidecars manually |
| Both checksum and file altered | Digest fetched from the same untrusted source | Verify via signed manifest or trusted channel |
| Cosign blob verify fails | File bytes differ, wrong bundle, or signer identity mismatch | Check exact file, bundle, issuer, and identity |
| Cosign image verify fails | Different image digest, signature unpublished, or unsupported registry | Resolve digest, check registry/referrers and signing output |
| Valid signature from unknown signer | Public key/certificate not in trust policy | Reject signer; check certificate identity/issuer |
| JAR signature warning | Certificate chain, timestamp, algorithm, or trust store issue | Read warnings with `-strict`; verify chain/algorithm/time |
| `jarsigner` passes yet JAR fails at runtime | JAR modified post-signing or packaging/loader issue | Verify final artifact, smoke-test exact signed JAR |
| Gradle dependency verification fails | New dependency or changed checksum/signature | Investigate source, review metadata before updating |
| Gradle verification bootstrap passes with malicious dependency | Baseline created from an already compromised repository | Cross-check checksums/keys with independent sources |
| Missing Maven checksum sidecar | Repository policy/transport did not provide expected file | Check repository manager policy; never skip integrity checks |
| Provenance subject digest mismatch | Attestation belongs to another image or artifact changed post-build | Regenerate provenance for the exact digest |
| Provenance has wrong source repo | Wrong builder/CI external parameters or self-asserted claim | Source provenance from trusted builder; enforce policy |
| SBOM lacks expected components | SBOM generated from source or a different image | Generate from exact final image digest |
| Image tag points to a new image | Mutable tag overwritten | Verify and deploy digest; never redeploy by tag |
| Private signing key exposed | Key stored in repo/logs/runner | Revoke/rotate, audit signatures, move to KMS/HSM |
| Lost signature bundle | Artifact published without saving verification material | Publish bundle/OCI referrer alongside release and back up metadata |

## 18. Practice Exercises with Answers

### Exercise 1 — Does a Checksum Prove the Publisher?

A JAR has a SHA-256 checksum matching `app.jar.sha256` downloaded from the same server. Can we conclude the JAR was released by the company?

**Answer:** not yet. A checksum only proves the file matches the sidecar digest. You need a signed digest or one fetched from an independent trusted source, plus signer identity verification.

### Exercise 2 — JAR Altered by One Byte

After signing a JAR with `jarsigner`, someone edits a resource inside the archive. What is the verification result?

**Answer:** verification of the signed entry must fail because the entry digest mismatches. Re-check using `jarsigner -verify -strict -verbose -certs`.

### Exercise 3 — Gradle Verification

**Question:** which files does `gradle/verification-metadata.xml` check?

**Answer:** dependencies/plugins/metadata resolved by Gradle's dependency engine per verification metadata. It does not automatically sign the local Spring Boot JAR built by the project; release artifacts require their own checksums/signatures.

### Exercise 4 — Cosign Keyless

**Question:** keyless signing avoids long-lived private keys, so is identity verification still needed?

**Answer:** yes. Verification must check that the OIDC issuer and certificate identity match an authorized workflow/repository; any arbitrary identity is insufficient.

### Exercise 5 — Tag and Digest

**Question:** image `app:1.0.0` was signed, but the registry tag later points to a different image. What should consumers deploy?

**Answer:** resolve and verify the specific image digest, then deploy that exact digest. A tag is only a mutable reference name.

### Exercise 6 — Self-Asserted Provenance

**Question:** a developer writes a JSON file listing commit and builder, then signs it with Cosign using a personal key. Can we claim build provenance is verified by a trusted builder?

**Answer:** no. The signature authenticates whoever signed the JSON; it does not prove a builder actually ran the build. Provenance must be generated by a trusted build platform, and policy must verify builder identity/subject.

### Exercise 7 — SBOM and Vulnerabilities

**Question:** an image has a validly signed SBOM. Can we conclude the image has zero CVEs?

**Answer:** no. An SBOM is an inventory; you must run a vulnerability scanner with a suitable database/policy and evaluate results at release time.

### Exercise 8 — Signing and Checksum Order

**Question:** a checksum was computed before `jarsigner` added signature files. After signing, does the old sidecar still match?

**Answer:** no. The JAR's bytes changed; compute the checksum and Cosign blob signature on the final signed JAR.

### Exercise 9 — Provenance Subject

**Question:** an attestation is signed, yet its subject digest does not match the image being deployed. Should it be accepted?

**Answer:** no. The attestation describes a different artifact; reject it and locate provenance matching the exact digest.

### Exercise 10 — Non-Reproducible Artifact

**Question:** two builds of the same commit yield different checksums. Can we conclude an attack occurred?

**Answer:** not yet. Investigate timestamps, archive ordering, tool versions, environment, and generated metadata. Reproducibility aids independent verification, yet differing checksums alone do not identify the root cause.

## 19. Pre-Publish Checklist

- [ ] Build the exact executable Boot JAR; test gate passed.
- [ ] Final artifact has deterministic name/version/path, not confused with plain JAR.
- [ ] SHA-256 or SHA-512 computed after all file-modifying steps.
- [ ] Digest published via signed manifest or independent trusted channel.
- [ ] If using jarsigner, certificate chain, timestamp, algorithm, and warnings reviewed.
- [ ] If using Cosign blob, bundle saved alongside artifact and identity/issuer checked.
- [ ] OCI image resolved to digest and signature bound to that exact digest.
- [ ] Provenance generated by trusted builder with subject digest matching artifact/image.
- [ ] Policy checks repository, commit/ref, builder ID, invocation, and external parameters.
- [ ] SBOM generated from exact final image/artifact and scanned.
- [ ] Gradle dependency verification or Maven dependency policy protects input dependencies.
- [ ] Private signing keys never placed in Git, build logs, images, or artifacts; KMS/HSM/secret manager used appropriately.
- [ ] Artifact, checksum, signature bundle, provenance, and SBOM stored in an auditable release record.
- [ ] Consumer verifies before publishing/deploying; verification errors fail the release gate.
- [ ] Deployment uses the verified image digest, never re-resolving a mutable tag.
- [ ] No secrets or unnecessary internal data included in public attestations.

**Conclusion:** checksums show whether bytes match a reference digest; signatures show who signed content under a trust policy; provenance shows which source/builder/inputs produced the artifact; SBOMs show what the product contains. With Spring Boot, build and test the final JAR, compute SHA-256, sign the JAR/blob or OCI image with a trusted signer, attach digest-bound provenance/SBOMs, and verify identity and claims before releasing. No single checksum file or signature alone replaces that full chain of controls.

## 20. Official Documentation

- Gradle — Dependency Verification (checksums, signatures, `verification-metadata.xml`): https://docs.gradle.org/current/userguide/dependency_verification.html
- Sigstore — Cosign Quickstart: https://docs.sigstore.dev/quickstart/quickstart-cosign/
- Sigstore — Signing Blobs: https://docs.sigstore.dev/cosign/signing/signing_with_blobs/
- Sigstore — Signing Containers: https://docs.sigstore.dev/cosign/signing/signing_with_containers/
- Sigstore — Verifying Signatures: https://docs.sigstore.dev/cosign/verifying/verify/
- Sigstore — In-Toto Attestations: https://docs.sigstore.dev/cosign/verifying/attestation/
- Sigstore — Security Model (Fulcio, OIDC, Rekor): https://docs.sigstore.dev/about/security/
- SLSA — Build Provenance v1: https://slsa.dev/spec/v1.1/provenance
- Apache Maven — Deploy Plugin: https://maven.apache.org/plugins/maven-deploy-plugin/
- Apache Maven — Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Java SE 17 — jarsigner command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Java SE 17 — MessageDigest API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- Java SE 17 — HexFormat API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html

CLI syntax, predicate aliases, and registry referrer support may vary across Cosign/Pack/Maven/Gradle versions. Before adopting into a release pipeline, pin tool versions, verify `--help`/version-specific docs, and test verification against the actual published artifact digest.