# Signed Artifacts with jarsigner

A **signed artifact** is a JAR file with an attached digital signature so that recipients can verify whether the contents have been modified after signing and identify the certificate containing the signer's public key. In Java, the **jarsigner** tool creates and verifies signatures for JAR or ZIP archives.

A signed JAR still contains the original classes, resources, and data. Signing does not encrypt the contents or hide files. It adds manifest digests, a signature file, and a signature block so that recipients can verify the integrity of each entry along with the publisher's signature.

Two outcomes must be distinguished: a **cryptographically valid signature** and a **signer trusted under the organization's or deployment environment's policy**. A JAR may pass digest checks while still using a self-signed certificate or an untrusted certificate chain.

## 1. What Is a Signed Artifact?

A JAR is a ZIP-based archive, typically containing class files, resources, configuration files, and a manifest. When signed with jarsigner, the archive is updated with signature metadata.

Example:

~~~text
hello-signed.jar
├── META-INF/
│   ├── MANIFEST.MF
│   ├── RELEASE.SF
│   └── RELEASE.RSA
└── com/
    └── example/
        └── Hello.class
~~~

The signature filenames in this example are derived from the alias **release**. If **-sigfile** is not specified, jarsigner uses up to the first eight characters of the alias, converted to uppercase, to name the **.SF** and signature block files.

A signed artifact can be distributed via a Maven repository, package registry, download server, or internal deployment system. Recipients can run jarsigner to verify the archive before installing it or loading it at runtime.

### What Does a Signature Protect?

A JAR signature allows verification of:

- Whether the contents of signed entries remain identical to when they were signed.
- Whether the signature file was signed with the private key corresponding to the public key in the certificate.
- Whether the manifest digests still match the digests recorded in the signature file.
- Whether the algorithms used for signing are disabled by the current JDK.

A signature does not:

- Encrypt classes or resources.
- Protect the publisher's private key after the private key has been compromised.
- Automatically prove that the publishing organization is trustworthy.
- Guarantee that the program is safe or free of malware.
- Protect entries added after signing without re-signing.
- Replace testing, code review, or dependency provenance checks.

A signed JAR can still be opened with a ZIP tool to inspect its contents. Anyone who has the archive can view the unencrypted classes and resources.

## 2. Three Signature Components in META-INF

When jarsigner signs a JAR, the tool updates the manifest and adds two groups of signature files to the **META-INF** directory.

### MANIFEST.MF — Per-Entry Digests

The manifest stores archive-wide attributes and individual sections for each entry. When signed with jarsigner, each protected file entry has a section containing the digest of the file's contents.

Illustrative example:

~~~text
Manifest-Version: 1.0

Name: com/example/Hello.class
SHA-384-Digest: <base64-digest>
~~~

The digest is computed over the bytes of the entry. If the contents of **Hello.class** change, the new digest will differ from the digest stored in the manifest.

The manifest may also contain application attributes such as **Main-Class**, **Class-Path**, **Implementation-Version**, and other attributes. These attributes have their own meaning in a JAR; they are not the digital signature itself.

### RELEASE.SF — Signature File

The **.SF** file contains the digest of the manifest or of each manifest section corresponding to an entry. It binds the manifest data to the digital signature.

Illustrative example:

~~~text
Signature-Version: 1.0
SHA-384-Digest-Manifest: <base64-manifest-digest>

Name: com/example/Hello.class
SHA-384-Digest: <base64-section-digest>
~~~

By default, the signature file includes headers containing the digest of the entire manifest and of the manifest header to optimize verification. If the full-manifest digest does not match, verification can fall back to checking the individual corresponding sections.

### RELEASE.RSA — Signature Block

The signature block file contains the digital signature generated from the **.SF** file using the private key, along with the certificate or certificate chain that authenticates the corresponding public key.

The file extension depends on the key algorithm:

| Extension | Common Key Algorithm |
|---|---|
| .RSA | RSA or RSASSA-PSS |
| .DSA | DSA |
| .EC | Elliptic Curve or EdDSA |

The signature block uses a PKCS#7 structure to store the signature and certificates. Recipients use the public key in the certificate to verify the signature of the **.SF** file.

### Chain of Verification

~~~text
Bytes of each entry
        |
        v
Digest in MANIFEST.MF
        |
        v
Digest of manifest section in RELEASE.SF
        |
        v
Digital signature of RELEASE.SF in RELEASE.RSA
        |
        v
Signer's public key and certificate chain
~~~

Each layer validates the layer beneath it. If the bytes of a signed entry are modified, the digest will not match and verification will fail.

## 3. How Does jarsigner Create a Signed Artifact?

jarsigner uses a private key stored in a keystore to sign a JAR. The alias points to the entry containing the private key; the accompanying certificate provides the public key and the signer's identity information.

General workflow:

1. Build a complete JAR from classes and resources.
2. Prepare a keystore containing the private key and certificate chain.
3. Select the alias of the key entry to use for signing.
4. Run jarsigner to update the manifest and generate the signature file and signature block.
5. Verify the output artifact.
6. Store the signed artifact and verification results in the release record.
7. Distribute the exact bytes of the verified artifact.

All additions, deletions, or modifications of entries should be completed before the signing step. After signing, do not modify the archive contents and distribute it without re-signing and re-verifying.

### Keystore and Alias

A keystore contains the private key along with its certificate chain. The alias identifies the entry containing the private key to use.

Example of generating an RSA key pair and self-signed certificate for a learning environment:

~~~bash
keytool -genkeypair \
  -alias release \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -dname "CN=Example Release, O=Example, C=VN" \
  -keystore release.p12 \
  -storetype PKCS12
~~~

keytool will prompt interactively for passwords. If no separate password is specified for the private key, the key password typically defaults to the keystore password.

A self-signed certificate is suitable for experimenting with the signing mechanism. It does not establish a publisher identity validated by a public CA.

### Signing a JAR and Writing a Separate Output

~~~bash
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -signedjar hello-signed.jar \
  hello.jar \
  release
~~~

Explanation:

- **-keystore release.p12** selects the keystore.
- **-storetype PKCS12** selects the keystore format.
- **-signedjar hello-signed.jar** writes the signed archive to a separate path.
- **hello.jar** is the unsigned input artifact.
- **release** is the alias of the private key entry.

If **-signedjar** is omitted, jarsigner overwrites the input JAR with the signed result. In a release workflow, writing to a separate output is recommended so that the input artifact is preserved for comparison and investigation.

Do not hardcode passwords directly on the command line or in release scripts. Let the tool prompt interactively or use a secret-provision mechanism appropriate for your build system.

## 4. Complete Example: Creating and Running a Signed JAR

This example uses Java 17 or later. The **javac**, **jar**, **keytool**, and **jarsigner** commands must come from the corresponding JDK.

### Source Structure

~~~text
signed-artifact-demo/
└── src/
    └── com/
        └── example/
            └── Hello.java
~~~

File **src/com/example/Hello.java**:

~~~java
package com.example;

public final class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from signed artifact.");
    }
}
~~~

### Step 1: Compile

From the project root directory:

~~~bash
javac --release 17 -d out src/com/example/Hello.java
~~~

This command creates the class file at **out/com/example/Hello.class**.

### Step 2: Create a JAR with Main-Class

~~~bash
jar --create \
  --file hello.jar \
  --main-class com.example.Hello \
  -C out .
~~~

Inspect the input JAR:

~~~bash
jar --list --file hello.jar
~~~

### Step 3: Create a Test Keystore

~~~bash
keytool -genkeypair \
  -alias release \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -dname "CN=Example Release, O=Example, C=VN" \
  -keystore release.p12 \
  -storetype PKCS12
~~~

In this example, a self-signed certificate is created for demonstration. For production releases, use a code signing certificate and trust chain in accordance with organizational policy.

### Step 4: Sign the Artifact

~~~bash
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -signedjar hello-signed.jar \
  hello.jar \
  release
~~~

### Step 5: Inspect the Signature Files

~~~bash
jar --list --file hello-signed.jar
~~~

The main signature entries are expected to look like:

~~~text
META-INF/MANIFEST.MF
META-INF/RELEASE.SF
META-INF/RELEASE.RSA
com/example/Hello.class
~~~

Entry order may vary. Other directories and entries depend on how the JAR was created. The **.SF** and **.RSA** filenames in this example come from the alias **release**.

### Step 6: Verify the Artifact

~~~bash
jarsigner -verify -verbose -certs hello-signed.jar
~~~

This command verifies the signature and displays certificate information when available. Because the example uses a self-signed certificate, the output may include warnings about the signer being self-signed or the certificate chain not being validated. That does not mean the digests and mathematical signature are necessarily invalid; it means the signer's identity has not been confirmed by an appropriate trust anchor.

### Step 7: Run the JAR

~~~bash
java -jar hello-signed.jar
~~~

Output:

~~~text
Hello from signed artifact.
~~~

Running successfully only proves that the program launches in that environment. You still need to inspect the signature, certificate chain, warnings, artifact provenance, and release policy.

### Differences Between Demo and Production

| Learning Demo | Production Release |
|---|---|
| Self-signed certificate | Code signing certificate per organizational policy |
| No public TSA required | Typically uses a trusted timestamp authority |
| Chain warnings may appear | Chain must be validated against trust policy |
| Test keystore file | Protected private key, potentially using HSM/token |
| Manual verification | Automated verification in CI/CD with -strict |

## 5. How Does jarsigner Verify a Signed Artifact?

When running:

~~~bash
jarsigner -verify hello-signed.jar
~~~

jarsigner performs these core verification steps:

1. Verifies the signature in the signature block against the **.SF** file.
2. Checks whether the digests in **.SF** match the corresponding sections of the manifest.
3. Reads each entry that has a corresponding section in **.SF**, recomputes the digest of its bytes, and compares it against the digest in the manifest.
4. Checks for the use of algorithms disabled by the JDK's security properties.

If a critical verification step fails, the tool reports an error rather than treating the artifact as valid.

### Signature Verification vs. Identity Verification

A signature may be mathematically valid because **.SF** was signed with the private key matching the public key in the certificate. However, that certificate could:

- Be a self-signed certificate.
- Lack a certificate chain leading to a trusted CA.
- Be expired or not yet valid.
- Have a KeyUsage or ExtendedKeyUsage that does not permit code signing.
- Have been revoked or have an unverifiable revocation status.
- Use an algorithm disabled by the JDK.

Therefore, read both the certificate details and jarsigner warnings. Do not rely solely on the **jar verified** line to make a release decision.

### Verifying with Detailed Output

~~~bash
jarsigner -verify -verbose -certs hello-signed.jar
~~~

Common flags in verbose output:

| Flag | Meaning |
|---|---|
| s | The entry's signature was verified |
| m | The entry is listed in the manifest |
| k | At least one certificate was found in the keystore |

The **k** flag only indicates that a matching certificate was found in the keystore being checked. It does not by itself prove that the certificate chain is trusted or that the publishing organization has been verified.

### Strict Verification

~~~bash
jarsigner -verify -strict hello-signed.jar
~~~

**-strict** causes the exit code to reflect severe warnings. Without **-strict**, some severe warnings may be displayed while the process still returns exit code 0. Therefore, release pipelines should use **-strict** and handle warnings according to policy.

Some important severe warnings:

- The signer certificate has expired or is not yet valid.
- The certificate chain is not validated.
- The signer certificate is self-signed.
- A disabled algorithm is used.
- The certificate lacks an appropriate KeyUsage for code signing.
- The JAR contains unsigned entries.
- Entries were signed by an alias other than the requested alias.

The self-signed example above may fail **-strict** due to trust warnings. This is expected in a test environment, not a production release configuration.

## 6. Signed Entries, Unsigned Entries, and Post-Signing Changes

jarsigner signs JAR file entries by recording digests in the manifest and signature file. However, signature status depends on when an entry is added to the archive.

### Modifying a Signed Entry

If a signed class or resource is later modified, the new digest will no longer match the digest in the manifest. During verification, jarsigner reports an integrity error.

Examples of actions that can break a signature:

- Replacing the contents of a class file.
- Replacing a signed resource or configuration file.
- Editing the manifest in a way that alters a signed section.
- Repackaging the archive after modifying entry contents.

Do not modify a signed artifact and redistribute it without re-signing the entire artifact according to the workflow.

### Adding New Entries After Signing

If a new file is added to a JAR after signing, the new entry may not have a digest in the existing signature file. Old entries may still verify successfully, but the JAR contains entries whose integrity has not been checked.

jarsigner has the severe warning **hasUnsignedEntry** for this case. This warning carries exit code bit 16 and is treated as an error under **-strict**.

Consequently, a verification run with no errors on old signatures is not enough to conclude that every entry in the archive is protected. Always check for unsigned entries and use **-strict** in CI.

### Correct Processing Order

1. Compile and package all classes and resources.
2. Add any required manifest attributes.
3. Inspect the JAR contents and dependencies.
4. Sign the artifact last.
5. Verify with jarsigner.
6. Record checksums, signatures, and verification results in the release record.
7. Distribute the exact verified file; do not modify the archive after signing.

## 7. Timestamps and Certificate Lifecycle

When signing a JAR, you can request a Time-Stamp Authority (TSA) to generate a timestamp for the signature.

The timestamp token is stored alongside the signature block. It provides proof of the signing time, helping systems evaluate whether the signer certificate was valid at the time of signing.

Example syntax:

~~~bash
jarsigner \
  -keystore release.p12 \
  -storetype PKCS12 \
  -tsa https://tsa.example.org \
  -signedjar hello-signed.jar \
  hello.jar \
  release
~~~

**https://tsa.example.org** is only an illustrative URL; replace it with an actual TSA endpoint trusted and authorized by your organization.

Related options:

| Option | Meaning |
|---|---|
| -tsa URL | Send a timestamp request to the TSA at URL |
| -tsacert alias | Select the TSA certificate in the keystore; the URL may be obtained from the certificate's SIA extension |
| -tsapolicyid OID | Specify the TSA policy identifier |
| -tsadigestalg algorithm | Select the digest algorithm for the timestamp request |

A timestamp does not make a signer certificate valid indefinitely. The TSA certificate, timestamp token, certificate chain, and associated algorithms must still be verified according to policy. Without a timestamp, a JAR may no longer verify after the signer certificate expires or after a future revocation point.

### Revocation Status Checking

The **-revCheck** option enables certificate revocation checking during signing or verification:

~~~bash
jarsigner -verify -revCheck hello-signed.jar
~~~

When enabled, jarsigner may need network access to fetch an OCSP response or CRL. Revocation checking is not enabled by default. Pipelines must account for network access, timeouts, and handling policies when the certificate status service is unavailable.

## 8. Digest and Signature Algorithms

The digest algorithm and signature algorithm are two separate components:

- **Digest algorithm** computes the hash of bytes in an entry or manifest.
- **Signature algorithm** uses the private key to sign the digest data or signature file.

Key options:

- **-digestalg**: specifies the digest algorithm for entries.
- **-sigalg**: specifies the signature algorithm, which must be compatible with the private key.

In Oracle JDK 24, jarsigner's default digest algorithm is SHA-384. The default signature algorithm is chosen based on the type and size of the private key. For example, a 3072-bit RSA key uses SHA384withRSA according to the JDK 24 defaults.

Do not pin an older algorithm solely for compatibility if it has been marked weak or disabled. The JDK uses security properties such as **jdk.jar.disabledAlgorithms** and **jdk.security.legacyAlgorithms** to evaluate algorithms. A JAR using a disabled algorithm may be treated as an unsigned JAR.

If older JDKs must be supported, verify compatibility across versions and choose algorithms that comply with security policy rather than arbitrarily downgrading security.

## 9. Multiple Signers for One Artifact

A JAR can be signed multiple times using different private keys. Each signing operation with a different alias creates a corresponding signature file and signature block pair.

Example:

~~~bash
jarsigner app.jar release-team-a
jarsigner app.jar release-team-b
~~~

An archive can contain multiple pairs of signature files, each representing one signer. Actual filenames are derived from the alias or **-sigfile**; different aliases should produce non-conflicting signature filenames.

Multiple signatures can be useful when approval from multiple teams is required. During verification, all signers, certificate chains, timestamps, and policies must be checked. Do not verify only a single alias if the workflow requires all specified signers.

## 10. Useful jarsigner Options for Working with Artifacts

| Option | Purpose |
|---|---|
| -keystore | Select the keystore used for signing or assisting certificate verification |
| -storetype | Select the keystore format |
| -signedjar | Write the signed artifact to a separate file |
| -sigfile | Set the base name for the .SF and signature block files |
| -digestalg | Select the digest algorithm |
| -sigalg | Select the signature algorithm |
| -verify | Verify the JAR signature |
| -verbose | Display detailed signing/verification output |
| -certs | Display certificate details during verbose verification |
| -strict | Turn severe warnings into a non-zero error exit code |
| -tsa | Request a timestamp from a TSA |
| -tsacert | Select the TSA certificate in the keystore |
| -revCheck | Enable certificate revocation status checking |
| -sectionsonly | Include only section digests in .SF; primarily used for testing |

Check the options supported by your installed JDK:

~~~bash
jarsigner -version
jarsigner -help
jarsigner -verify -help
~~~

Not every JDK or provider shares the same default algorithms and security policies. Verify the actual toolchain used in your release pipeline.

## 11. Integrating Signed Artifact Verification into CI/CD

A release pipeline should build the artifact and verify the exact file that will be distributed.

Reference workflow:

1. Build the application and package the JAR.
2. Run unit tests, integration tests, and dependency checks.
3. Obtain the signer alias and keystore from secret management or a signing service.
4. Sign the JAR with jarsigner.
5. If required, request a TSA timestamp.
6. Run **jarsigner -verify -verbose -certs**.
7. Run **jarsigner -verify -strict** and handle any severe warnings.
8. Inspect the signer certificate, chain, expiry, usage, and timestamp.
9. Compute the checksum of the signed artifact and store it with the release metadata.
10. Publish the exact verified artifact to the repository or deployment target.

Example verification step in CI:

~~~bash
jarsigner -verify -strict -verbose -certs build/app-signed.jar
~~~

If the command returns a non-zero exit code, the pipeline must halt the release and save diagnostics for investigation.

### Storing Release Evidence

With each release, store:

- Artifact name and version.
- SHA-256 checksum of the final JAR file.
- Signer certificate fingerprint.
- Certificate subject and issuer.
- Signature algorithm and digest algorithm.
- Timestamp and TSA identity, if present.
- Output of **jarsigner -verify -strict**.
- JDK vendor/version and build identifier.
- List of unsigned entries, if any; production releases should typically reject this case.

A checksum helps identify the exact released artifact. It does not replace a digital signature; checksums must be distributed over a trusted channel or protected within release metadata.

## 12. Signed JARs vs. Other Artifact Types

jarsigner is designed for JAR and ZIP archives. It does not replace operating-system code signing tools for other formats.

| Artifact | Common Signing Mechanism |
|---|---|
| JAR | jarsigner |
| JAR-structured ZIP | jarsigner |
| Windows EXE/MSI | Authenticode and Windows signing tools |
| macOS app/PKG/DMG | Apple code signing and notarization |
| Container image | Container ecosystem image signatures |
| Maven/Gradle metadata | Repository checksums and corresponding artifact signature mechanisms |

A release may include JARs, native launchers, installers, and container images. Each artifact type requires an appropriate signing and verification workflow. A JAR signature does not automatically protect an outer installer or container that packages it.

## 13. Common Errors When Verifying Signed Artifacts

### Unsigned JAR or Missing Signature Files

Possible causes include an unsigned artifact, deleted signature files, or unparseable signature files. Check with:

~~~bash
jar --list --file app.jar
~~~

Look for **META-INF/MANIFEST.MF**, the **.SF** file, and the corresponding signature block. If missing, confirm you have the right artifact and build stage.

### Digest Mismatch

An entry or manifest section was modified after signing. Use verbose output to locate the failing entry, rebuild the JAR from source, and re-sign after all changes are complete.

### Unsigned Entries

A file was added after the last signing pass, or only a subset of entries was protected. **-strict** can detect the **hasUnsignedEntry** severe warning. Inspect the entire archive and re-sign the complete artifact.

### Self-Signed Certificate or Unvalidated Chain

The signature may be mathematically valid, but the certificate chain does not lead to an accepted trust anchor. Use a certificate compliant with release policy, install the trust anchor properly, and inspect the certificate chain.

### Expired or Not-Yet-Valid Certificate

Check the system clock, certificate validity period, and timestamp token. If the artifact was signed while the certificate was valid, a valid timestamp can allow evaluating the signature as of the signing time; the TSA chain and policy must still be verified.

### Disabled Algorithm

The JDK may reject or treat a JAR as unsigned if the signature/digest algorithm is listed in **jdk.jar.disabledAlgorithms**. Use a currently supported algorithm and re-sign with the appropriate toolchain.

### Alias Does Not Match Signer

When passing an alias after the JAR name in a verify command, jarsigner may report that entries were not signed by the specified alias. Check the actual signer in the signature block and the alias in the keystore.

### Invalid Timestamp or TSA Chain

Check the TSA certificate, timestamp token, policy, validity period, and service reachability. Do not ignore TSA errors just to make a pipeline pass.

### Revocation Check Failure

When using **-revCheck**, the OCSP/CRL endpoint may be unreachable or the certificate may be revoked. Check network, proxy, firewall, and certificate status; follow the organization's approved fail-open/fail-closed policy.

## 14. Pre-Release Checklist for Signed Artifacts

- Finish building all classes, resources, and metadata before signing.
- Select the correct input JAR and output artifact.
- Use a private key entry authorized for release signing.
- Protect the keystore/private key and passwords using secret management.
- Verify the signer certificate, subject, issuer, validity, and key usage.
- Choose digest/signature algorithms compatible with the target JDK.
- Use a trusted timestamp authority if required by the release workflow.
- Verify with **jarsigner -verify -verbose -certs**.
- Use **-strict** in CI to catch severe warnings.
- Confirm that every entry requiring protection is signed.
- Do not modify the JAR after signing.
- Verify the certificate chain and trust policy independently of digest checks.
- Store checksums and signer details with the release evidence.
- Test the exact signed artifact in the runtime/deployment environment.
- If the release includes EXE, MSI, PKG, DMG, or container images, run the dedicated signing workflow for each type.

## 15. Key Terms to Remember

| Term | Meaning |
|---|---|
| Signed artifact | An artifact with a digital signature to verify integrity and signing origin |
| JAR | A ZIP archive containing Java classes, resources, and metadata |
| Manifest | The META-INF/MANIFEST.MF file containing general attributes and per-entry sections |
| Digest | A hash value of entry bytes or a manifest section |
| Signature file | The .SF file containing digests of the manifest/sections |
| Signature block | The .RSA, .DSA, or .EC file containing the signature and certificates |
| Signer | The entity owning the private key used to sign the artifact |
| Certificate chain | The chain of certificates linking the signer to a CA/trust anchor |
| TSA | Time-Stamp Authority that issues timestamp tokens |
| Timestamp | Proof of signing time certified by a TSA |
| Unsigned entry | An entry lacking a digest protected by the corresponding signature |
| -strict | Converts severe warnings into an error exit code |
| -revCheck | Enables certificate revocation checking via OCSP/CRL |
| Trust anchor | A root certificate configured as a point of trust |
| Code signing | The mechanism of digitally signing software to verify publisher origin and integrity |

A signed JAR artifact is part of the software supply chain. Sign after the build completes, verify all entries and signer certificates, handle warnings strictly in CI, use timestamps appropriately, and distribute the exact verified bytes.

## References

- Oracle JDK 24 — The jarsigner Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html
- Oracle JDK 24 — JAR File Specification: https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html
- Oracle JDK 24 — The keytool Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html
- Oracle JDK 24 — Java Security Developer's Guide: https://docs.oracle.com/en/java/javase/24/security/security-developer-guide.pdf