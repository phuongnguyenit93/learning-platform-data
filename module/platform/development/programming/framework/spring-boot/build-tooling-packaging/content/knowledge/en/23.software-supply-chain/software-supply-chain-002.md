# Verifying Checksums and Signatures According to Each Tool's Capabilities

In the software supply chain, a JAR file, dependency, or container image can be replaced during download, storage, build, or release. Two mechanisms commonly used to detect this are **checksums (hashes)** and **digital signatures**.

They answer two different questions:

- **Checksum:** do the received file contents match a trusted expected digest?
- **Digital signature:** was the data signed with the private key corresponding to a public key we trust to belong to the publisher?

A SHA-256 matching the expected digest confirms **integrity against an expected value**. It does not by itself prove who created the file. A valid signature proves the data was signed by the corresponding private key; to conclude it came from the expected publisher, you must verify the **key fingerprint and identity** through a trusted channel.

| Tool | Target | Primary capability |
| --- | --- | --- |
| sha256sum, PowerShell Get-FileHash, Java MessageDigest | Any file | Computes hashes and compares against a trusted checksum |
| Gradle Dependency Verification | Dependencies, plugins, and metadata resolved by Gradle | Checksums and PGP signatures according to reviewed metadata |
| Maven Resolver | Artifacts downloaded from Maven repositories | Checks sidecar checksums according to repository policy |
| Maven GPG Plugin / GnuPG | Published Maven artifacts | Creates and verifies detached OpenPGP signatures |
| JDK jarsigner / keytool | Java JAR/ZIP | Verifies entry signatures and signer certificates |
| Sigstore Cosign | OCI container images and blobs | Verifies signatures bound to a digest, key, or OIDC identity |

This lesson uses Java 17 and Gradle/Maven examples to explain how each tool works. Never embed private keys, passwords, or fake checksums in source code.

## 1. Checksums, Hashes, and Digital Signatures

### 1.1. A Hash Is a Fingerprint of Bytes

A cryptographic hash function takes input data of arbitrary length and returns a fixed-length digest. SHA-256 produces a 256-bit digest, typically represented as 64 hexadecimal characters:

~~~text
artifact.jar --SHA-256--> 64-character hexadecimal digest
~~~

Changing even a single byte of the file changes the digest with overwhelming probability. Hashes are useful for detecting corrupted files or files that differ from a recorded copy.

| Algorithm | Digest length | Notes |
| --- | --- | --- |
| MD5 | 128-bit | Do not use against adversaries |
| SHA-1 | 160-bit | Practical collision attacks exist; avoid for new security use cases |
| SHA-256 | 256-bit | Common choice for integrity |
| SHA-512 | 512-bit | Strong choice with a longer digest |

**Hashing is not encryption.** Standard SHA-256 does not use a private key. Anyone with the file can compute its digest.

### 1.2. Why a Checksum Alone Does Not Prove Origin

Suppose you download two files from the same server:

~~~text
app.jar
app.jar.sha256
~~~

If the server or publishing account is compromised, an attacker can replace both the JAR and the checksum. The two files will still match, yet the artifact could be malicious.

Therefore, the expected checksum must come from an **independently authenticated source**: a signed release manifest, a protected repository, a CI release record with controlled access, or the publisher's official channel. Downloading both the artifact and the checksum from the same untrusted source does not provide independent verification.

### 1.3. Digital Signatures Add Signer Authentication

The publisher uses a **private key** to sign the artifact or its digest/metadata. The consumer uses the corresponding public key to verify:

~~~text
Publisher:
  artifact bytes -> hash -> private key -> digital signature

Consumer:
  artifact + signature
       |
  trusted public key / certificate
       |
  verify signature + signer identity
       |
     PASS / FAIL
~~~

Digital signatures protect signed data against undetected modification. However, a mathematically valid signature alone does not prove the signer is the expected publisher. You must verify the fingerprint/key identity, certificate chain, issuer, validity period, and revocation status where applicable.

### 1.4. When to Use Both?

| Verification method | Integrity | Publisher authentication |
| --- | --- | --- |
| SHA-256 against a trusted expected digest | Yes | Not inherently |
| Checksum fetched from the same untrusted source as the file | Only detects accidental corruption; does not prevent simultaneous replacement | No |
| Signature with an authenticated key | Yes | Yes, within the scope of trust policy |
| Valid signature with an unverified key | Yes | Insufficient |
| SHA-256 + signature + trusted key fingerprint | Yes | Stronger basis |

Gradle also distinguishes checksums for verifying integrity and signatures for verifying provenance. Both can be combined; if a dependency is unsigned, a verified checksum serves as the fallback. [Gradle: Securing Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html).

## 2. Verifying Checksums with OS Tools

### Linux

~~~bash
sha256sum app.jar
~~~

This command prints the digest and filename. Compare the digest with the value from an authenticated release record.

If the sidecar uses GNU coreutils format:

~~~bash
sha256sum --check app.jar.sha256
~~~

Not every repository checksum sidecar includes the filename in the format expected by sha256sum --check. If the sidecar contains only a hex string, read the digest and compare it appropriately.

### macOS

~~~bash
shasum -a 256 app.jar
~~~

### Windows PowerShell

~~~powershell
Get-FileHash -Algorithm SHA256 .\app.jar
~~~

The output includes Hash and Algorithm fields. Compare Hash against the checksum obtained from a trusted source. Never compute a hash and immediately treat it as the publisher's expected value.

PowerShell check snippet:

~~~powershell
$expected = $env:EXPECTED_SHA256
$actual = (Get-FileHash -Algorithm SHA256 .\app.jar).Hash

if ($actual -eq $expected) {
    'RESULT=PASS'
} else {
    'RESULT=FAIL'
    exit 1
}
~~~

The EXPECTED_SHA256 variable must be supplied by the CI/release process from a verified manifest. If the variable is empty or malformed, the pipeline should fail early.

### On Checksum Mismatch

1. Stop using the artifact and do not deploy it.
2. Verify that the right file/version/platform was downloaded.
3. Check the source of the expected checksum and the file transfer process.
4. Check repository mirrors/caches, proxies, or potential artifact replacement.
5. Re-download from an authenticated source or ask the publisher to investigate.
6. Only update the expected checksum after independent confirmation and review.

**Never generate a new checksum and overwrite the expected value just to turn a build green.** Doing so can turn a supply-chain alert into acceptance of a tampered artifact.

## 3. Java 17: Checking SHA-256 with MessageDigest

The Java standard library provides java.security.MessageDigest. The following program takes a file path and an expected SHA-256, then prints RESULT=PASS or RESULT=FAIL.

### File Sha256Verifier.java

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class Sha256Verifier {

    private Sha256Verifier() {
    }

    public static void main(String[] args)
            throws IOException, NoSuchAlgorithmException {

        if (args.length != 2 || !args[1].matches("[0-9a-fA-F]{64}")) {
            System.err.println(
                    "Usage: java Sha256Verifier <file> <expected-sha256>");
            System.exit(2);
            return;
        }

        byte[] expected = HexFormat.of().parseHex(args[1]);
        MessageDigest digest = MessageDigest.getInstance("SHA-256");

        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            byte[] buffer = new byte[8192];
            int count;

            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        byte[] actual = digest.digest();

        if (MessageDigest.isEqual(expected, actual)) {
            System.out.println("RESULT=PASS");
        } else {
            System.out.println("RESULT=FAIL");
            System.exit(1);
        }
    }
}
~~~

Compile and run:

~~~bash
javac Sha256Verifier.java
java Sha256Verifier app.jar "$EXPECTED_SHA256"
~~~

EXPECTED_SHA256 must be supplied from an authenticated release manifest. If the file matches, stdout is exact:

~~~text
RESULT=PASS
~~~

If the file does not match:

~~~text
RESULT=FAIL
~~~

The program exits with code 1 on mismatch, code 2 on invalid arguments, and code 0 on pass. It streams the file without loading the entire artifact into RAM; MessageDigest.isEqual compares the two byte arrays. The expected checksum must still be authenticated from a trusted source before passing it to the program.

Do not design custom hash functions. Use standard algorithms and verified JDK/tool implementations.

## 4. Gradle Dependency Verification

Gradle includes a **Dependency Verification** mechanism. When a project contains the file:

~~~text
gradle/verification-metadata.xml
~~~

Gradle automatically uses this metadata to verify artifacts and metadata resolved by its dependency management engine. The scope covers:

- External JAR/ZIP dependencies.
- POMs, Ivy descriptors, and Gradle Module Metadata.
- Project and settings plugins.
- Artifacts resolved through dependency resolution APIs.

This mechanism does not check every file on disk. According to Gradle documentation, changing dependencies such as SNAPSHOTs and artifacts built locally within the project itself are outside the scope of dependency verification. [Gradle dependency verification](https://docs.gradle.org/current/userguide/dependency_verification.html).

### 4.1. Generating Metadata with SHA-256

From the project root:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

Gradle resolves the configurations, calculates SHA-256 digests, and creates/updates gradle/verification-metadata.xml.

To generate both checksums and PGP signatures:

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

Gradle supports MD5, SHA-1, SHA-256, and SHA-512, though SHA-256/SHA-512 are safer choices for modern verification. Gradle only supports signature verification with ASCII-armored .asc PGP signatures published on remote repositories. Not every artifact has a signature. [Gradle checksum and signature verification](https://docs.gradle.org/current/userguide/dependency_verification.html).

### 4.2. Example Entry in Verification Metadata

An entry looks like:

~~~xml
<component group="com.google.guava"
           name="failureaccess"
           version="1.0.3">
    <artifact name="failureaccess-1.0.3.jar">
        <pgp value="BDB5FA4FE719D787FB3D3197F6D4A1D411E9D1AE"/>
        <sha256 value="cbfc3906b19b8f55dd7cfd6dfe0aa4532e834250d7f080bd8d211a3e246b59cb"/>
    </artifact>
</component>
~~~

This is a structural example from the Gradle documentation. In a real project, values must match your exact verified dependencies/versions and keys; do not copy this sample entry to verify another artifact.

The configuration section can enable signature verification:

~~~xml
<configuration>
    <verify-metadata>true</verify-metadata>
    <verify-signatures>true</verify-signatures>
</configuration>
~~~

When verify-signatures is enabled, Gradle looks for the corresponding PGP signature and verifies it against trusted keys. If an artifact has no signature, a declared checksum can serve as a fallback. The metadata must contain sufficient information for all artifacts actually resolved.

### 4.3. Trusted Keys Must Be Verified Independently

Gradle stores trusted public keys in the verification metadata/keyring. When adding a key:

- Use the **full 40-character fingerprint** for PGP key/trusted-key entries, not just a short key ID.
- Verify the fingerprint on the publisher's official website or via an independent channel.
- Document the source and trust rationale in the metadata where appropriate.
- Check for key rotations and revocation notices.
- Do not automatically trust a key merely because it was downloaded from a keyserver.

A signature can be mathematically valid while having been created with an attacker's key. Trust policy is what determines whether that key represents the expected publisher. [Gradle trusted keys](https://docs.gradle.org/current/userguide/dependency_verification.html).

### 4.4. Bootstrapping Requires Review

write-verification-metadata records information from the artifacts Gradle currently resolves. If a repository or cache was compromised before bootstrapping, Gradle could write the checksum/signature metadata of a malicious artifact into the baseline.

After bootstrapping:

1. Review the diff of verification-metadata.xml and the keyring.
2. Verify checksums from independent sources whenever possible.
3. Cross-check trusted key fingerprints against official sources.
4. Inspect entries with origin="Generated by Gradle"; they do not imply independent verification.
5. Update origins/trust notes after review.
6. Commit the metadata to version control so developers and CI share the same baseline.

**Bootstrapping creates a convenient baseline; it does not automatically prove every dependency is safe.** [Gradle bootstrapping guidance](https://docs.gradle.org/current/userguide/dependency_verification.html).

### 4.5. Handling Verification Failures

When a checksum mismatches or a signature is untrusted:

- Do not delete the failing entry just to let the build proceed.
- Identify the artifact coordinates, repository URL, filename, and expected metadata.
- Verify the checksum/key on official sources.
- Investigate mirrors/caches/local repositories if the same artifact yields different bytes when downloaded.
- If the publisher rotated keys, verify the new fingerprint and review it as a security change.
- Only update metadata after confirming the new artifact is genuine.

Gradle generates detailed reports on verification failures. For verbose console output, configure:

~~~properties
org.gradle.dependency.verification.console=verbose
~~~

Metadata applies across the entire build, including root and subprojects. When a dependency/plugin version changes, update the metadata under review; do not assume Gradle automatically knows old entries are obsolete.

## 5. Maven: Checksum Policy and PGP/GPG Signatures

Maven has two distinct capabilities:

1. **Maven Resolver checksum policy:** checks sidecar checksums when downloading artifacts from a repository.
2. **GPG/PGP signatures:** the publisher signs artifacts/POMs; the consumer verifies the signature and public key identity through an appropriate process.

Maven checksum policy does not replace PGP signer verification.

### 5.1. Setting Checksum Policy to Fail

Maven repository policy supports:

| Value | Behavior |
| --- | --- |
| fail | Fails resolution when a checksum is invalid or missing |
| warn | Warns when a checksum is invalid or missing |
| ignore | Skips checksum checks |

Current Maven documentation notes the default is warn in Maven 3 and fail in Maven 4 and later. Because behavior depends on Maven version, projects requiring strict enforcement should configure fail explicitly. [Maven settings checksumPolicy](https://maven.apache.org/settings.html).

Configuration snippet inside a repository:

~~~xml
<releases>
    <enabled>true</enabled>
    <checksumPolicy>fail</checksumPolicy>
</releases>
<snapshots>
    <enabled>false</enabled>
    <checksumPolicy>fail</checksumPolicy>
</snapshots>
~~~

This snippet is for a releases repository. If using a snapshot repository, enable snapshots and apply the corresponding policy. Similar configuration can be placed in pluginRepository to check plugin artifacts.

Checksum policy checks checksums provided by the repository. If an attacker can replace both the artifact and the sidecar checksum in the same repository, this mechanism does not independently authenticate the publisher; a digital signature or another trust channel is required.

### 5.2. Checksum and Signature Requirements When Publishing to Maven Central

Under current Sonatype Central publishing requirements:

- Uploaded files must have valid checksum sidecars; .md5 and .sha1 are required, while .sha256 and .sha512 are supported.
- Uploaded files must have corresponding .asc GPG/PGP detached signatures.
- Signature/checksum files must accompany artifacts, POMs, and required published files.

These are **Central publishing compatibility requirements**; they do not mean MD5/SHA-1 are algorithms you should pick for new security controls. For internal integrity controls, prefer SHA-256/SHA-512 and strong signatures/key identities. Check the latest Central policy at release time. [Sonatype Central publishing requirements](https://central.sonatype.org/publish/requirements/).

### 5.3. Signing Artifacts with Maven GPG Plugin

Apache Maven GPG Plugin provides the gpg:sign goal to sign project artifacts, POMs, and attached artifacts using GnuPG. This goal binds to the verify phase by default in the plugin documentation. [Maven GPG Plugin sign goal](https://maven.apache.org/plugins/maven-gpg-plugin/sign-mojo.html).

Example configuration:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-gpg-plugin</artifactId>
    <version>3.2.8</version>
    <configuration>
        <bestPractices>true</bestPractices>
    </configuration>
    <executions>
        <execution>
            <id>sign-artifacts</id>
            <phase>verify</phase>
            <goals>
                <goal>sign</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Version 3.2.8 is an example based on current plugin documentation; projects should select a version compatible with their Maven/JDK and verified policy. bestPractices enables plugin enforcement of credential-protection practices.

Run:

~~~bash
mvn verify
~~~

The plugin invokes GnuPG to sign artifacts/POMs/attached artifacts per execution. Private keys must not be stored in the repository, POM, or public build files.

### 5.4. Protecting Passphrases and Private Keys

Maven GPG Plugin recommends using gpg-agent/pinentry or secret environment mechanisms for non-interactive environments, depending on plugin/GnuPG configuration. Avoid:

- Writing passphrases directly in the POM.
- Passing plaintext passwords on the command line.
- Committing private keys to Git.
- Printing secrets into Maven/CI logs.

Use keys protected by a hardware token, HSM, secret manager, or signing service if supported by the organization. Only authorized release jobs should have access to the private key. [Maven GPG Plugin security practices](https://maven.apache.org/plugins/maven-gpg-plugin/).

### 5.5. Verifying Detached Signatures with GnuPG

Suppose the publisher provides:

~~~text
app-1.2.3.jar
app-1.2.3.jar.asc
~~~

The consumer runs:

~~~bash
gpg --verify app-1.2.3.jar.asc app-1.2.3.jar
~~~

GnuPG checks the signature file against the artifact bytes. However, you must also verify:

- Is the signature valid?
- Does the public key fingerprint match the key published by the publisher?
- Is the key expired, revoked, or rotated?
- Has the identity in the key been independently verified?

Inspect fingerprints:

~~~bash
gpg --fingerprint
~~~

Compare the **full fingerprint** with the value published by the publisher over an authenticated channel. A Good signature message only indicates the signature is valid under the key being used; it does not by itself prove that key belongs to the right publisher.

### 5.6. Sidecar Checksums and PGP Signatures

~~~text
artifact.jar
artifact.jar.sha256  -> checksum (integrity against trusted value)
artifact.jar.asc     -> detached PGP signature (signer + integrity)
~~~

If only .sha256 is present, the expected digest must come from a trusted source. If .asc is present, a trusted public key/fingerprint is needed. When both exist, verify both in parallel for stronger assurance.

## 6. JDK jarsigner and keytool: Signing and Verifying Java JARs

The JDK provides:

- jarsigner: signs and verifies JAR/ZIP files.
- keytool: creates/manages keystores, key pairs, and certificate entries; prints certificate fingerprints.

JAR signatures are typically stored in META-INF, including a .SF signature file and a .RSA, .DSA, or .EC signature block depending on the key/algorithm. Verification checks signatures and digests of signed entries. Oracle JDK 17 documentation also describes warnings when unsigned entries or certificate chain issues exist. [JDK 17 jarsigner documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html).

### 6.1. Generating a Demo Key

Strictly for local learning experiments, generate a key pair and self-signed certificate:

~~~bash
keytool -genkeypair -alias demo-signer -keyalg RSA -keysize 3072 -validity 3650 -keystore demo-signing.p12 -storetype PKCS12 -dname "CN=Demo Signer, O=Example"
~~~

Keytool prompts interactively for a password. This is a **self-signed demo key**, does not represent a real publisher identity, and must not be used as a production signing key. Do not add demo-signing.p12 to the repository.

Production private keys must be managed with proper security processes, access control, backup, rotation, and auditing.

### 6.2. Signing a JAR

~~~bash
jarsigner -keystore demo-signing.p12 -storetype PKCS12 -signedjar app-signed.jar app.jar demo-signer
~~~

This command creates app-signed.jar from app.jar. Use a separate output file to preserve the original; if signedjar is omitted, jarsigner updates the input file by default.

Do not pass passwords on the command line; let the tool prompt or use an appropriate protection mechanism.

### 6.3. Verifying the Signature

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

When the signature and signed entries are valid, the output typically includes jar verified. Read all warnings, not just the final line.

In CI, you can require severe warnings to fail the command:

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

strict reflects severe warnings in the exit code. With a self-signed demo key, self-signed/untrusted warnings are expected; they do not prove publisher identity has been authenticated. Real releases require proper certificate chains and trust policies.

### 6.4. Inspecting the Signer Certificate and Fingerprint

~~~bash
keytool -printcert -jarfile app-signed.jar
~~~

This command prints certificate details from the signed JAR, including the SHA-256 fingerprint. Compare the fingerprint against a value published by the publisher via an independent channel. Oracle recommends verifying the fingerprint with the sender or a secure public key source before trusting/importing a certificate. [JDK 17 keytool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html).

**Do not automatically trust a certificate merely because it is embedded in the JAR.** An attacker can sign with their own key and embed their own certificate. Out-of-band fingerprint comparison is what establishes whether the key belongs to the expected publisher.

### 6.5. Limitations of JAR Signatures

- Does not prove code is free of vulnerabilities.
- Does not prove the signer reviewed the source code.
- Does not replace dependency scanning.
- Does not protect entries added after signing if they remain unsigned.
- Does not ensure the certificate chain is trusted if trust anchors are missing.
- Does not replace provenance or checksums from another trusted source.

Sign **after packaging is complete**. If you modify, repack, or add content after signing, you must re-sign and re-verify. Unsigned entry warnings must be investigated because those entries are not integrity-protected by the signature.

## 7. Sigstore Cosign: Verifying OCI Container Image Signatures

JAR signatures are not a dedicated mechanism for OCI images. For container images, a widely used tool is **Cosign** in the Sigstore ecosystem.

OCI images are referenced by tag or digest:

~~~text
registry.example.com/team/orders-api:1.2.3
registry.example.com/team/orders-api@sha256:...
~~~

Tags are human-readable but can be reassigned depending on registry policy. Digests are content-addressed references pointing to specific content. When verifying a deployment, obtain the digest from a trusted release/registry record and verify that exact reference.

**A digest alone does not prove who published the image.** If an attacker replaces both the image and the digest a system consumes, signature/identity trust is still needed to authenticate the publisher.

### 7.1. Verifying with a Public Key

When the publisher releases a verified public key:

~~~bash
cosign verify --key cosign.pub "$IMAGE_REF"
~~~

IMAGE_REF must contain a digest-based image reference obtained from a trusted release record/registry, in the form registry/repository@sha256:... . The public key cosign.pub must be distributed/authenticated via an independent trust channel.

The Cosign signature payload binds to the image digest; by default, the verify command checks both the signature and the digest claim for standard Cosign payloads. [Sigstore Cosign verification](https://docs.sigstore.dev/cosign/verifying/verify/).

### 7.2. Keyless Verification with OIDC Identity

In CI environments supporting OpenID Connect, Cosign can create keyless signatures bound to a certificate identity issued by an OIDC issuer. Consumers must verify both the expected identity and the expected OIDC issuer:

~~~bash
cosign verify "$IMAGE_REF" --certificate-identity="$EXPECTED_IDENTITY" --certificate-oidc-issuer="$EXPECTED_ISSUER"
~~~

EXPECTED_IDENTITY and EXPECTED_ISSUER must come from a verified release policy, such as the identity of the release workflow and the CI system's issuer. Avoid overly broad wildcards when policy requires restricting to a specific repository/workflow.

Cosign supports verification with traditional keys or keyless identities; both approaches require clear trust policies. [Cosign keyless verification](https://docs.sigstore.dev/cosign/verifying/verify/).

### 7.3. Image Signing Flow in CI

1. Build the image.
2. Push the image to an authorized registry.
3. Capture the digest of the pushed image.
4. Sign that exact digest using the release workflow's signing key or OIDC identity.
5. Verify signature/identity/digest before deployment.
6. Record the digest and verification result in the release record.

Do not merely sign a tag and ignore the digest actually deployed by the pipeline. A tag can be updated after signing; the digest is the content identifier that must be bound.

### 7.4. Signatures Do Not Replace Attestations and Vulnerability Scans

A Cosign image signature verifies the signature against trust policy and the image digest. It does not automatically prove the source code was reviewed, the build used the right source commit, the build process was uncompromised, or the image has no CVEs.

To verify the build process, use provenance/SLSA attestations and verify them under a separate policy. To check for CVEs, use SBOMs and vulnerability scanners. The three layers answer different questions: **who signed it**, **where/how it was built**, and **what vulnerable components exist**.

## 8. Comparing Tools by Artifact Type

| Need | Tool | What the tool does | Limitation |
| --- | --- | --- | --- |
| Check a downloaded JAR file | SHA-256 utility | Compares bytes against expected digest | Does not authenticate signer with checksum alone |
| Automatically verify Gradle dependencies | Dependency Verification | Verifies checksums/signatures per metadata | Does not cover local build outputs and changing dependencies |
| Check Maven repository checksums | Maven Resolver | Fails/warns/ignores when sidecar is missing/wrong | Does not replace PGP signer verification |
| Sign a Maven release | Maven GPG Plugin | Signs artifacts/POMs/attached artifacts | Consumer still needs to verify key/fingerprint |
| Verify a Java signed JAR | jarsigner / keytool | Verifies entries/signatures/certificates | Must check certificate trust and unsigned entries |
| Verify an OCI image | Cosign | Verifies signatures bound to digest, key, or OIDC identity | Does not replace vulnerability/provenance checks |

Choose the tool by the question:

- **“Was the file altered?”** → SHA-256 from a trusted source.
- **“Are Gradle dependencies the approved versions?”** → Gradle verification metadata.
- **“Does the Maven repository have valid checksums?”** → Maven checksum policy; if signer proof is needed, verify PGP separately.
- **“Who signed this JAR?”** → jarsigner + certificate fingerprint/trust chain.
- **“Does the deployed image carry the release workflow's signature?”** → Cosign with digest and identity/issuer.
- **“Which source commit built this image?”** → provenance attestation, not just an image signature.

## 9. Sample Verification Chain for a Spring Boot Release

Suppose a release pipeline produces:

~~~text
orders-api-1.2.3.jar
orders-api-1.2.3.jar.sha256
orders-api-1.2.3.jar.asc
orders-api:1.2.3
~~~

A workflow can be organized as:

1. **Verify artifact file:** compute SHA-256 via OS tools or Sha256Verifier and compare against an authenticated release manifest. Stop on mismatch.
2. **Verify file signature:** if .asc exists, run GPG verify and compare the public key fingerprint against the publisher's official fingerprint. If the JAR uses a Java code signing certificate, run jarsigner -verify -strict and keytool -printcert.
3. **Verify dependency baseline:** run the Gradle build with a reviewed/committed gradle/verification-metadata.xml. CI fails if any dependency/plugin checksum or signature differs from baseline.
4. **Build and verify image:** capture the digest after push and verify the Cosign signature using a public key or expected OIDC identity/issuer. Deploy using the digest reference.
5. **Store release provenance:** retain source commit, Gradle/Maven version, JDK/toolchain, artifact SHA-256, JAR signer fingerprint, OCI image digest, Cosign identity/issuer, verification result, and CI run.

Provenance fields must come from the real release system—never fabricate placeholder data. A release may use some or all verification layers depending on artifact type and policy.

## 10. Key Management, Fingerprints, and Certificate Lifecycle

### 10.1. Public Keys Must Come from Trusted Sources

Public keys can be fetched from a keyserver or registry, but the storage location does not authenticate identity by itself. Compare full fingerprints against official websites, release documentation, verified support channels, or an organization-managed trust store.

Do not rely solely on a signer name in GPG, an email in a certificate, a short key ID, a public key downloaded alongside an artifact from an untrusted mirror, or a Good signature message without checking the fingerprint.

### 10.2. Key Rotation

When a publisher rotates keys:

1. Confirm the key rotation announcement through an official channel.
2. Verify the new key's fingerprint.
3. Determine the start/end dates for accepting the old key.
4. Update Gradle verification metadata, GPG keyrings, certificate trust stores, or Cosign policies.
5. Review the changes and run build/verify in CI.
6. Remove the old key on schedule once no releases require verification with it.

If a key is compromised/revoked, handle it under incident policy rather than treating all historical signatures as automatically safe.

### 10.3. Certificate Expiry and Timestamps

For JAR signing using X.509 certificates, check validity periods, chains, key usage, algorithms, and timestamps. A JAR can be signed while the certificate is valid with a trusted timestamp, yet warnings and runtime/JDK policies must still be inspected. jarsigner -strict helps turn severe warnings into errors in automation.

### 10.4. Protecting Private Keys

- Only signing jobs should have permission to sign.
- Use HSM/KMS or a signing service when feasible.
- Use a secret manager/agent; never commit private keys.
- Prevent credentials from appearing in logs and shell history.
- Audit who signed, when, and which artifact digest was signed.
- Maintain rotation/revocation plans and secure backups.

## 11. Common Issues and How to Handle Them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| SHA-256 differs from expected | Wrong version, transfer error, different mirror, or tampered file | Stop using it; verify source, path, and release manifest |
| Hash matches yet artifact is malicious | Expected checksum came from the same compromised source | Verify signatures and obtain checksums via an independent channel |
| Gradle checksum verification failed | Artifact differs from baseline or repository/cache issue | Check coordinates, file, repository, and review metadata |
| Gradle untrusted PGP key | New key, missing keyring entry, or attacker key | Verify full fingerprint via publisher before adding |
| Many Generated by Gradle origins | Unsigned artifacts or unverified signatures/keys | Review each entry; cross-check official checksums/signatures |
| Maven only warns on checksum mismatch | Checksum policy is set to warn | Configure fail and investigate the sidecar |
| Maven downloads artifacts without checking PGP | Checksum policy does not perform PGP verification | Verify .asc with GnuPG or a dedicated tool |
| GPG reports Good signature from unknown signer | Signature is valid for the current key, but the key is unverified | Compare full fingerprint and identity via official sources |
| jarsigner reports verified with warnings | Self-signed/expired certificate, broken chain, or unsigned entries | Read warnings, use strict, inspect certs/entries |
| JAR signature fails after build | File was modified/repacked after signing | Sign after final packaging and re-verify |
| keytool prints certificate but trust is unknown | A certificate inside a JAR is not automatically trusted | Compare fingerprint out of band; check chain/issuer |
| Cosign finds no signature | Image is unsigned, wrong repo/digest, or registry lacks signatures | Check release flow and image reference |
| Cosign identity/issuer mismatch | OIDC certificate does not match policy-accepted identity/issuer | Check expected identity/issuer; do not relax policy arbitrarily |
| Same image tag has different digest | Tag was retagged or image rebuilt | Verify/deploy by digest; investigate provenance |
| Valid signature yet image has CVEs | Signatures are not vulnerability scans | Scan SBOM and update dependencies/base image |
| CI passes but developer machine fails | Different trust stores, JDK/GPG/Cosign versions, or keyrings | Standardize toolchain and verification metadata |
| Build passes with warm cache, fails on clean machine | Local cache masked missing metadata/checksums/signatures | Test in clean environments and store trust metadata in VCS |

### Rule for Handling Mismatches

**Never add a new checksum/key just to bypass an error.** A verification failure is an event to investigate. If a publisher changed an artifact/version or signing key, verify the source, reason, and timing before updating the baseline under review.

## 12. Per-Tool Checklists

### Checksum Files

- [ ] Use SHA-256 or SHA-512.
- [ ] Expected digest comes from an authenticated release record/source.
- [ ] Correct artifact path/version/platform.
- [ ] Fail the pipeline on mismatch.
- [ ] Never overwrite expected digests on error.

### Gradle Dependency Verification

- [ ] gradle/verification-metadata.xml is present in the repository.
- [ ] Baseline generated for required configurations/plugins.
- [ ] Checksum entries reviewed.
- [ ] Full trusted PGP fingerprints verified.
- [ ] Signature verification enabled where signatures exist and keys are trusted.
- [ ] Metadata/keyring committed to version control.
- [ ] Update process defined when dependency/plugin versions change.
- [ ] Remember changing dependencies/local build outputs are outside this mechanism's scope.

### Maven

- [ ] Repository checksum policy set to fail when enforcement is required.
- [ ] Do not confuse checksum policy with PGP signature verification.
- [ ] Releases include .asc signatures per publishing policy.
- [ ] Public key fingerprints verified independently.
- [ ] Private keys/passphrases managed via agent/secret manager.
- [ ] Latest checksum/signature requirements of target repository checked.

### Java JAR

- [ ] Sign after all edits/repackaging steps complete.
- [ ] jarsigner -verify -strict runs during release validation.
- [ ] No unintended unsigned entries.
- [ ] Certificate chain, validity, algorithm, and timestamp checked.
- [ ] Signer fingerprint matches a trusted source.

### OCI Image

- [ ] Use image digest to identify content to deploy.
- [ ] Cosign signature is bound to that digest.
- [ ] Verify public key or OIDC identity/issuer per policy.
- [ ] Check provenance attestation when build process verification is required.
- [ ] Scan SBOM/vulnerabilities separately.
- [ ] Record digest and verification result in the release record.

## 13. Self-Check Questions

**Question 1.** Does a matching SHA-256 prove a file was released by the right publisher?

**Answer:** No. It proves the bytes match the expected digest. Publisher identity requires signatures and trusted keys/identities.

**Question 2.** Why is downloading both a file and its checksum from the same compromised source insufficient?

**Answer:** An attacker can replace both. You need checksums from an independently authenticated source or signatures bound to trusted keys/identities.

**Question 3.** Where does Gradle Dependency Verification store its baseline?

**Answer:** gradle/verification-metadata.xml in the project root; metadata is applied to builds whenever the file exists.

**Question 4.** Does write-verification-metadata sha256,pgp automatically guarantee every dependency is safe?

**Answer:** No. It bootstraps metadata from currently resolved artifacts. Independent review of checksums and trusted key fingerprints is still required.

**Question 5.** Does Maven checksumPolicy=fail verify the GPG signer?

**Answer:** No. It enforces sidecar checksums; detached PGP signatures must be verified separately.

**Question 6.** Does jarsigner -verify passing prove the certificate belongs to the right company?

**Answer:** Not yet. You must check the chain and compare the SHA-256 fingerprint against information published by the publisher over a trusted channel.

**Question 7.** Why should jarsigner -strict be used in CI?

**Answer:** Because some severe warnings can be printed without producing a non-zero exit code unless strict is enabled; CI needs to fail according to security policy.

**Question 8.** How do an OCI image digest and a Cosign signature differ?

**Answer:** The digest identifies the image content; the signature authenticates the signer and binds to the digest. A digest alone does not prove who published it.

**Question 9.** Does a passing Cosign signature prove an image has no CVEs?

**Answer:** No. Separate SBOM/vulnerability scanning and remediation are required.

**Question 10.** When Gradle reports an untrusted PGP key, should you immediately add the key ID from the error to trusted metadata?

**Answer:** No. Verify the full fingerprint via an independent publisher source first, then review adding the key.

## 14. Official Documentation

- Gradle — [Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksums, PGP signatures, trusted keys, bootstrapping, and metadata file.
- Apache Maven — [Settings Reference](https://maven.apache.org/settings.html): checksumPolicy ignore/warn/fail.
- Apache Maven — [Maven GPG Plugin](https://maven.apache.org/plugins/maven-gpg-plugin/): signing artifacts and POMs with GnuPG.
- Apache Maven — [gpg:sign goal](https://maven.apache.org/plugins/maven-gpg-plugin/sign-mojo.html): phase/goal and best practices.
- Sonatype Central — [Publishing Requirements](https://central.sonatype.org/publish/requirements/): checksum files and GPG/PGP signatures.
- Oracle JDK 17 — [jarsigner Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html): signing/verifying JARs, certificate chains, warnings, and strict mode.
- Oracle JDK 17 — [keytool Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): fingerprints, certificates, and keystores.
- Sigstore — [Cosign Signature Verification](https://docs.sigstore.dev/cosign/verifying/verify/): verifying image signatures, digest claims, and OIDC identity/issuer.

**Remember:** Checksums answer **“do the bytes match the expected value?”**; signatures answer **“who signed this data and is that key trusted?”**. Gradle, Maven, JDK, and Cosign support different verification layers. A trustworthy release requires expected checksums/key identities with clear provenance, automated CI verification, strict handling of mismatches, and retained digests/provenance for traceability.