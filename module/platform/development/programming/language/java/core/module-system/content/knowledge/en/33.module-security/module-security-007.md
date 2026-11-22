# Signed JARs, Certificates, and Artifact Verification

## 1. Objective

A JAR can contain classes, resources, and also a module descriptor. When releasing a library or application, recipients need to know two things: whether the artifact contents have been altered after signing, and whether the certificate used to sign belongs to a publisher they trust.

Java supports signing and verifying JARs with `jarsigner`, and managing key pairs and certificates with `keytool`. These two tools are commonly used together in the release workflow:

1. Generate or obtain a certificate bound to the publisher's public key.
2. Use the corresponding private key to sign the JAR.
3. Publish the signed JAR along with necessary certificate and checksum information.
4. Recipients verify the signature, certificate chain, signer identity, and checksum before placing the artifact into their runtime environment.

A JAR signature provides integrity evidence for signed entries and links the signature to the signer certificate. A signature does not encrypt JAR contents and does not by itself prove that software is safe.

After this lesson, you can:

- Distinguish between private key, public key, certificate, and keystore.
- Generate a key pair for test environments and understand the CA-issued certificate workflow.
- Sign a JAR using `jarsigner`.
- Verify signatures and inspect certificate details using `jarsigner` and `keytool`.
- Compare SHA-256 and distinguish between checksums, signatures, and artifact provenance.
- Inspect the module descriptor of a signed modular JAR.

## 2. Components in the Signing Workflow

| Component | Role |
| --- | --- |
| Private key | Publisher's secret used to create signatures. Must be protected in a keystore or key management system. |
| Public key | Public part of the key used to verify signatures. |
| Certificate | Digital document binding a public key to an identity or organization, signed by a CA or self-signed. |
| Keystore | Storage for key pairs and certificate chains; e.g., PKCS12 format. |
| JAR signature | Signature data and digests for entries in the archive. |
| Checksum | Hash value of the entire artifact file, used to compare two copies byte-for-byte. |

A certificate does not contain the private key. You can distribute the certificate and public key, whereas the release signing private key must remain secret.

A certificate issued by a trusted CA helps recipients verify the trust chain and signer identity per their policy. A self-signed certificate can still be used for testing and integrity checking, but recipients must have an independent way to confirm that the public key genuinely belongs to the publisher.

## 3. Preparing a Keystore and Certificate

### Generating a Key Pair for Testing

You can use `keytool` to generate an RSA key pair and self-signed certificate in a PKCS12 keystore:

~~~bash
keytool -genkeypair \
    -alias release \
    -keyalg RSA \
    -keysize 3072 \
    -sigalg SHA256withRSA \
    -validity 365 \
    -storetype PKCS12 \
    -keystore release.p12 \
    -dname "CN=Example Release, O=Example, C=VN"
~~~

Explanation:

- `-alias release`: identifier name for the entry in the keystore.
- `-keyalg RSA` and `-keysize 3072`: generates an RSA key pair with the specified key size.
- `-sigalg SHA256withRSA`: signature algorithm used for the certificate.
- `-validity 365`: certificate validity period in days.
- `-storetype PKCS12`: uses the PKCS12 keystore format.
- `-keystore release.p12`: file storing the private key and certificate.
- `-dname`: Distinguished Name of the certificate subject.

The command will prompt for the keystore password and private key password. Never put real passwords directly in scripts, command history, or project documentation.

This is a self-signed certificate suitable for labs. In production, certificates must be issued and verified according to organizational policy or a CA trusted by recipients.

### CA-Issued Certificate Workflow

For real release certificates, the workflow is typically:

1. Generate a key pair in a keystore or key management system.
2. Create a Certificate Signing Request (CSR) from the public key and organization details.
3. Submit the CSR to a CA per identity verification procedures.
4. Receive the signer certificate along with the intermediate/root certificate chain.
5. Import the certificate reply into the exact alias containing the corresponding private key.
6. Inspect subject, issuer, validity period, key usage, and chain before signing artifacts.

You can generate a CSR with:

~~~bash
keytool -certreq \
    -alias release \
    -keystore release.p12 \
    -storetype PKCS12 \
    -file release.csr
~~~

The CA returns a certificate for the public key in the CSR. When importing the certificate reply, use the exact alias/key pair that generated the CSR and ensure the certificate chain is properly established.

### Viewing Certificates in a Keystore

~~~bash
keytool -list -v \
    -keystore release.p12 \
    -storetype PKCS12 \
    -alias release
~~~

The output helps inspect the alias, entry type, subject, issuer, serial number, validity period, and certificate chain. For an entry containing a private key, the keystore manages the private key alongside its corresponding certificate chain.

## 4. Signing a JAR with `jarsigner`

Suppose an artifact has been built:

~~~text
build/
└── app.jar
~~~

Use the `release` alias to sign and produce a separate output file:

~~~bash
jarsigner \
    -keystore release.p12 \
    -storetype PKCS12 \
    -signedjar app-signed.jar \
    app.jar release
~~~

Where:

- `-keystore`: specifies the store containing the private key and certificate.
- `-storetype`: keystore format.
- `-signedjar`: name of the signed output JAR.
- `app.jar`: input artifact.
- `release`: alias of the private key used for signing.

The tool may prompt for keystore and private key passwords. Retrieve passwords from an appropriate secret management mechanism; do not commit them to Git or print them in CI logs.

If `-signedjar` is omitted, `jarsigner` can update the signature directly in the input JAR. In a release pipeline, creating a separate output file keeps the unsigned artifact for comparison and easier traceability.

### What Gets Written Into the JAR?

A signed JAR typically has files in `META-INF/`, for example:

~~~text
META-INF/
├── MANIFEST.MF
├── RELEASE.SF
└── RELEASE.RSA
~~~

Exact filenames depend on the signer and algorithm. The manifest file stores digests of entries; the `.SF` file contains digests related to the manifest; the signature block file such as `.RSA`, `.DSA`, or `.EC` contains the signature and certificates needed for verification.

When a recipient verifies, the tool checks signatures and digests to detect whether entry contents were modified compared to what was signed.

## 5. Verifying a JAR Signature

Basic command:

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

Meaning:

- `-verify`: verifies signatures in the JAR.
- `-verbose`: displays detailed per-entry information.
- `-certs`: displays certificate information associated with signers.

A successful result may end with the message:

~~~text
jar verified.
~~~

However, do not look at this line alone and conclude the artifact was signed by a trusted publisher. The output can also include warnings about self-signed certificates, untrusted certificates, expiration, missing timestamps, or algorithms no longer recommended.

Strict mode can be used:

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

`-strict` causes warnings related to certificates and signatures to be treated more strictly and can cause the command to return an error exit code. In CI, check the exit code and archive verification output as evidence for the release step.

When reading verbose output, pay attention to each entry:

- Signed entries must have an appropriate verification status.
- Unsigned entries may appear as unsigned.
- Entries modified after signing will fail digest verification.
- If a JAR has multiple signers, determine which signer signed each entry.

A JAR can contain both signed and unsigned entries. If release policy requires all classes/resources to be protected, confirm no critical application entries were left unsigned.

## 6. Inspecting the Certificate Used for Signing

You can extract certificate information directly from the JAR:

~~~bash
keytool -printcert -jarfile app-signed.jar
~~~

This command displays the signer certificate in the JAR, typically including subject, issuer, serial number, validity period, fingerprints, and algorithm information.

If you have a separate certificate file:

~~~bash
keytool -printcert -file signer.cer
~~~

When verifying a signer, check:

- **Subject:** does the identity recorded in the certificate match the expected publisher?
- **Issuer:** which CA issued the certificate?
- **Validity:** does the signing time fall within the certificate's validity period?
- **Certificate chain:** can a chain be built to an accepted trust anchor?
- **Fingerprint:** does the fingerprint match the value published by the publisher through an independent channel?
- **Key usage and algorithm:** do the certificate and algorithm comply with the organization's code-signing policy?

A self-signed certificate allows cryptographic signature verification, yet it does not establish identity trust on its own. To trust a self-signed certificate, recipients must verify the fingerprint through a trusted channel and explicitly configure trust according to their policy.

## 7. Checksums and Signatures Answer Two Different Questions

A SHA-256 checksum tells whether two files have the same byte contents. A JAR signature verifies signed entries and binds them to a signer certificate.

Compute the checksum of the signed artifact:

On Linux/macOS:

~~~bash
sha256sum app-signed.jar
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash .\app-signed.jar -Algorithm SHA256
~~~

Compare the hash against the value published through a trusted channel. If the downloaded file has a different hash from the reference value, it is not a byte-for-byte copy of what was published.

Do not treat a checksum downloaded from the exact same server distributing the artifact as independent proof: if both the artifact and the checksum file are replaced, the two values can still match.

| Mechanism | What Is Checked | What It Does Not Prove by Itself |
| --- | --- | --- |
| SHA-256 checksum | Whether all bytes of the file match a reference value. | Who created the file or whether the file is safe. |
| JAR signature | Whether signed entry digests are valid and the signature matches the signer's public key. | Whether that certificate belongs to a publisher the recipient trusts. |
| Certificate chain validation | Whether the certificate chains to a trust anchor accepted by policy. | That the source code has no vulnerabilities or the artifact is non-malicious. |
| Build provenance/attestation | Which source, workflow, and build environment produced the artifact per provided evidence. | Absolute quality or safety of sources and dependencies. |

A good release process may use signatures, checksums, and provenance together. Each mechanism adds a different type of evidence.

## 8. Timestamps and Certificate Validity

Certificates have a validity period. If a signer certificate expires after release, recipients still need reliable proof that the artifact was signed while the certificate was valid.

JAR signing supports timestamps from a Time Stamping Authority (TSA). When signing, a TSA endpoint can be provided:

~~~bash
jarsigner \
    -keystore release.p12 \
    -storetype PKCS12 \
    -tsa <tsa-url> \
    -signedjar app-signed.jar \
    app.jar release
~~~

Replace `<tsa-url>` with a TSA endpoint approved by the organization. The TSA issues a timestamp token binding the signing time with TSA evidence.

A trusted timestamp helps evaluate when a signature was created relative to the certificate's validity window. It does not turn an untrusted certificate into a trusted certificate; recipients still need to check the chain, TSA policy, and certificate status according to their requirements.

## 9. What Invalidates a Signature?

After signing, do not arbitrarily modify the contents of signed entries.

For example, the following operations can cause verification to fail:

- Modifying a signed class or resource.
- Editing the manifest after signing.
- Repacking the JAR in a way that changes entry bytes.
- Changing the module descriptor after signing.
- Running a repackaging tool that inadvertently strips or corrupts signature data.

If an artifact needs changes, rebuild from source, run tests, and re-sign the final artifact. Never sign first and then add resources or alter release contents.

A JAR signature protects signed entries according to digests stored in the signature structure. Therefore, inspect verification output to know which entries are signed and whether any were modified, especially when an artifact combines multiple inputs or passes through multiple CI steps.

## 10. Verifying a Modular JAR

A modular JAR has a `module-info.class` module descriptor. JAR signatures and module descriptors serve two separate purposes:

- The module descriptor declares the module name, dependencies, package `exports`/`opens`, and service `uses`/`provides`.
- The JAR signature protects the integrity of signed entries and binds contents to a signer.

After signing, you can inspect the module descriptor:

~~~bash
jar --describe-module --file app-signed.jar
~~~

If you need to list archive contents:

~~~bash
jar --list --file app-signed.jar
~~~

And verify the signature:

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

`jar --describe-module` displaying a valid descriptor does not replace signature verification. Conversely, a valid signature does not prove the descriptor has the right dependencies or exports for the intended architecture.

If `module-info.java` changes, recompile and repackage the modular JAR, then sign the new artifact. If you need to verify module name, version, `requires`, `exports`, `uses`, or `provides`, read the descriptor and compare it against the expected release configuration.

## 11. Recommended Release and Verification Workflow

### Publisher Side

1. Build the artifact from an identified commit.
2. Run tests and quality checks.
3. Inspect the module descriptor if the artifact is a modular JAR.
4. Sign the exact final artifact using a protected private key.
5. Re-verify the JAR after signing with `jarsigner -verify`.
6. Compute the SHA-256 of the signed file.
7. Store build evidence, certificate fingerprint, checksum, and provenance per release policy.
8. Distribute the artifact alongside verification details through official channels.

### Recipient Side

1. Download the artifact and checksum/signature details from the distribution source.
2. Verify SHA-256 against a reference value obtained from a trusted channel.
3. Run `jarsigner -verify -strict -verbose -certs`.
4. Check subject, issuer, validity, fingerprint, and certificate chain.
5. Confirm the signer matches the expected publisher per trust policy.
6. Inspect the module descriptor and dependencies if the artifact is used on the module path.
7. Only admit the artifact into build or runtime after all required verification steps pass.

If the signature is valid but the certificate is untrusted, stop to verify the signer's identity. If the checksum mismatches, re-fetch the artifact from the official source and investigate the discrepancy. Do not ignore warnings merely to keep a pipeline running.

## 12. Takeaways

- Signing private keys must be protected; public certificates bind public keys to signer identities.
- `keytool` creates and manages key pairs, CSRs, certificates, and keystores.
- `jarsigner` signs JARs and verifies signatures.
- `jarsigner -verify -strict -verbose -certs` enables stricter checks and displays related certificates.
- `keytool -printcert -jarfile` displays certificates used in a JAR.
- SHA-256 checksums compare full file bytes; JAR signatures verify signed entries and signers.
- A valid signature does not imply a trusted certificate, and a trusted certificate does not imply safe software.
- Sign after completing build/packaging; any subsequent content modification requires re-signing.
- For modular JARs, verify both the module descriptor and the artifact signature separately.

When releasing Java libraries or applications, treat artifact verification as part of the delivery workflow: check bytes, signatures, signer identity, and module structure before use.