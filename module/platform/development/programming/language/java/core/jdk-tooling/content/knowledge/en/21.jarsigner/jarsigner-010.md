# Signing Key Management in Java

Signing key management is the process of generating, protecting, using, rotating, and revoking key pairs used to authenticate the origin and integrity of artifacts. In the Java ecosystem, the primary tools are **keytool** for managing keystores and certificates, and **jarsigner** for signing and verifying JAR signatures.

A basic workflow includes:

1. Generating a key pair consisting of a private key and a public key.
2. Creating a certificate signing request (CSR) from the public key.
3. Receiving the CA-issued certificate and importing the certificate chain into the keystore.
4. Using the private key to sign the JAR with jarsigner.
5. Verifying the signature and the signer's certificate.
6. Storing, backing up, rotating, and retiring keys according to policy.

Example command to generate a key pair in a PKCS12 keystore:

~~~bash
keytool -genkeypair \
    -alias release-2026 \
    -keyalg RSA \
    -keysize 3072 \
    -sigalg SHA256withRSA \
    -dname "CN=Example Release Signing, OU=Release, O=Example, C=VN" \
    -validity 365 \
    -keystore release.p12 \
    -storetype PKCS12
~~~

After obtaining an appropriate certificate, use jarsigner:

~~~bash
jarsigner \
    -keystore release.p12 \
    -storetype PKCS12 \
    -digestalg SHA-256 \
    -sigalg SHA256withRSA \
    -signedjar app-signed.jar \
    app.jar \
    release-2026
~~~

The signing command uses the private key stored under the alias release-2026. In a real environment, release-signing certificates are typically issued by a CA or an authorized organization; self-signed certificates are only suitable for labs or privately controlled environments.

## 1. Key Pairs, Certificates, and Digital Signatures

A key pair consists of two mathematically related keys:

- **Private key:** secret, used to create digital signatures. Only the owner or an authorized signing system may use it.
- **Public key:** can be shared publicly, used to verify signatures created by the corresponding private key.

An X.509 certificate binds a public key to the identity of a subject and is signed by an issuer. A certificate does not contain a private key.

In the JAR signing process:

1. jarsigner uses the private key to generate a signature for the JAR contents.
2. The signature and signer certificate are stored in the archive.
3. The recipient uses the public key in the certificate to verify the signature.
4. Trust policy determines whether that certificate represents a trusted signer.

Digital signatures support two properties:

- **Integrity:** detects whether signed content has been modified.
- **Authenticity:** verifies that the signature was created by the private key corresponding to the public key in the certificate.

JAR signing does not encrypt the archive contents. Recipients can still read classes, resources, and the manifest inside the JAR.

A cryptographically valid signature also does not by itself prove that a program is safe. It proves that the content matches the signature and identifies which signer key signed it; trusting the signer's identity requires an appropriate certificate chain and trust policy.

## 2. Keystore, Truststore, and Aliases

A **keystore** is a repository for security entries. Depending on the entry type, it can contain private keys, certificate chains, or secret keys.

A **truststore** typically contains trusted certificates, such as CA certificates or peer certificates accepted by an organization. Technically, keystores and truststores can use the same format; the main difference is their intended purpose and contents.

Common entry types:

| Entry type | Contents | Use case |
|---|---|---|
| PrivateKeyEntry | Private key and certificate chain | JAR signing, server or client identity |
| trustedCertEntry | A trusted public certificate | Truststore, CA or peer certificate |
| SecretKeyEntry | Symmetric key | Application-level data encryption |

An entry has an **alias** to identify it within the keystore. For example, release-2026 is the alias of the key entry used to sign releases. An alias is only an identifier, not an access-control or key-encryption mechanism.

You can list entries:

~~~bash
keytool -list -keystore release.p12 -storetype PKCS12
~~~

View details:

~~~bash
keytool -list -v -keystore release.p12 -storetype PKCS12
~~~

View only a specific alias:

~~~bash
keytool -list -v \
    -keystore release.p12 \
    -storetype PKCS12 \
    -alias release-2026
~~~

## 3. Choosing a Keystore Format

Common formats:

- **PKCS12:** the standard format, widely supported, and the default choice of keytool on modern JDKs.
- **JKS:** the legacy Java KeyStore format, still supported for compatibility with legacy systems.
- **PKCS11/HSM:** uses a provider and a hardware security module or token to keep private keys outside regular keystore files.

Create a PKCS12 keystore:

~~~bash
keytool -genkeypair \
    -alias release-2026 \
    -keyalg RSA \
    -keysize 3072 \
    -keystore release.p12 \
    -storetype PKCS12
~~~

Create a JKS keystore when required by legacy systems:

~~~bash
keytool -genkeypair \
    -alias legacy-release \
    -keyalg RSA \
    -keysize 2048 \
    -keystore legacy.jks \
    -storetype JKS
~~~

Do not rename the file extension to convert formats. Use keytool -importkeystore to migrate entries and verify the result.

PKCS12 may have different password and key-protection rules than JKS depending on the provider. Some providers require the private key password to match the keystore password. Check provider and target system compatibility before standardizing password provisioning.

## 4. Generating a Key Pair with keytool

Basic syntax:

~~~bash
keytool -genkeypair [options]
~~~

Example generating an RSA key pair for release signing:

~~~bash
keytool -genkeypair \
    -alias release-2026 \
    -keyalg RSA \
    -keysize 3072 \
    -sigalg SHA256withRSA \
    -dname "CN=Example Release Signing, OU=Release, O=Example, C=VN" \
    -validity 365 \
    -ext KU=digitalSignature \
    -ext EKU=codeSigning \
    -keystore release.p12 \
    -storetype PKCS12
~~~

Parameters:

| Option | Meaning |
|---|---|
| -alias | Entry name in the keystore |
| -keyalg | Key pair generation algorithm |
| -keysize | Key size |
| -groupname | Key group name, typically used with certain elliptic curve algorithms |
| -sigalg | Certificate signature algorithm |
| -dname | Subject Distinguished Name |
| -validity | Validity period in days for the initial self-signed certificate |
| -ext | X.509 extension declaration |
| -keystore | Keystore path |
| -storetype | Keystore format |

The option KU=digitalSignature declares the key usage purpose for digital signatures. EKU=codeSigning indicates code-signing usage when supported by the certificate profile and CA. CA policies may require specific extensions or algorithms.

Generating a key pair also creates an initial self-signed certificate to bind the public key to the entry. This certificate is not yet a certificate issued by a public or organizational CA.

### Choosing Algorithms

Choose algorithms based on security policy, runtime compatibility, CA requirements, and the signing system:

- RSA with an appropriate key size, such as 3072 bits, is usually widely compatible.
- ECDSA with curves supported by the organization and platform, such as P-256 or P-384.
- Use a modern digest such as SHA-256 or stronger per policy.
- Do not choose MD5 or SHA-1 for new signing workflows.
- Avoid choosing overly outdated algorithms solely for compatibility with unpatched systems.

There is no single configuration suitable for every environment. Confirm which algorithms are accepted by the CA, JDK, operating system, verification tools, and release regulations.

### Password Prompting During Creation

If -storepass or -keypass is omitted, keytool can prompt for passwords interactively. This is more suitable for manual operations because passwords are not exposed in plain text on the command line.

Do not use example passwords like changeit for production keys.

## 5. Creating a Certificate Signing Request (CSR)

When using an internal or external CA, do not send the private key to the CA. Generate a CSR from the existing key pair:

~~~bash
keytool -certreq \
    -alias release-2026 \
    -keystore release.p12 \
    -storetype PKCS12 \
    -file release-2026.csr
~~~

The CSR contains the Subject information and public key along with a signature created by the corresponding private key. The private key remains in the keystore.

Extensions can be specified if required by the CA and permitted by the certificate issuance process:

~~~bash
keytool -certreq \
    -alias release-2026 \
    -keystore release.p12 \
    -storetype PKCS12 \
    -file release-2026.csr \
    -ext KU=digitalSignature \
    -ext EKU=codeSigning
~~~

Submit the CSR to the CA according to organizational procedures. The CA verifies identity and policy before issuing the certificate.

Inspect the CSR before sending:

~~~bash
keytool -printcertreq -file release-2026.csr
~~~

A CSR is not an issued certificate. Do not use CSR output to conclude that a certificate chain or trust is already valid.

## 6. Importing the Certificate Reply and Chain from the CA

After the CA issues the certificate, retrieve the certificate reply along with any required intermediate/root certificates according to the CA's process.

You can import a CA certificate into the keystore under a separate alias if needed:

~~~bash
keytool -importcert \
    -alias example-intermediate-ca \
    -file intermediate-ca.cer \
    -keystore release.p12 \
    -storetype PKCS12
~~~

Then import the certificate reply for the alias holding the private key:

~~~bash
keytool -importcert \
    -trustcacerts \
    -alias release-2026 \
    -file release-reply.pem \
    -keystore release.p12 \
    -storetype PKCS12
~~~

The certificate reply must match the public key in the release-2026 entry. keytool verifies this relationship before replacing the self-signed certificate with the CA-issued certificate.

If the CA provides the chain in PKCS#7 format or a single file containing multiple certificates, use the appropriate reply file according to the CA's instructions. If an intermediate certificate is missing, import the appropriate CA certificate first or supply the complete chain.

After importing, verify:

~~~bash
keytool -list -v \
    -keystore release.p12 \
    -storetype PKCS12 \
    -alias release-2026
~~~

Confirm that:

- The entry is still a PrivateKeyEntry.
- The certificate chain length is reasonable.
- The Owner/Subject matches the release identity.
- The Issuer matches the CA.
- The validity period and extensions meet requirements.
- The certificate chain matches CA records.

Do not import an unfamiliar certificate just because keytool asks whether to trust it. Verify the fingerprint through an independent channel before confirming.

## 7. Inspecting the Certificate and Public Key Before Signing

View the alias certificate:

~~~bash
keytool -list -v \
    -keystore release.p12 \
    -storetype PKCS12 \
    -alias release-2026
~~~

Export the public certificate:

~~~bash
keytool -exportcert -rfc \
    -alias release-2026 \
    -keystore release.p12 \
    -storetype PKCS12 \
    -file release-2026.cer
~~~

View the fingerprint:

~~~bash
keytool -printcert -v -file release-2026.cer
~~~

Fields to inspect:

- Subject/Owner: signer identity.
- Issuer: CA that issued the certificate.
- Serial number: certificate identifier within the issuer's scope.
- Validity: Not Before and Not After.
- SHA-256 fingerprint: certificate identification value.
- Public Key Algorithm: public key algorithm and size.
- Key Usage and Extended Key Usage: intended purposes.
- Certificate chain: CA path.

Exporting a certificate only exports public data. It does not export the private key. You can share the certificate or fingerprint so recipients can verify the signer, but never share the keystore file containing the private key.

## 8. Signing a JAR with jarsigner

jarsigner signs a JAR using a private key in a keystore.

Syntax:

~~~bash
jarsigner [options] jar-file alias
~~~

Example creating a separate output file to preserve the unsigned JAR:

~~~bash
jarsigner \
    -keystore release.p12 \
    -storetype PKCS12 \
    -digestalg SHA-256 \
    -sigalg SHA256withRSA \
    -signedjar app-signed.jar \
    app.jar \
    release-2026
~~~

Meaning:

- -keystore specifies where the private key is stored.
- -storetype specifies the keystore format.
- -digestalg selects the digest algorithm used to hash contents.
- -sigalg selects the signature algorithm.
- -signedjar specifies the output signed JAR filename.
- app.jar is the input JAR.
- release-2026 is the alias containing the private key and certificate chain.

If -signedjar is omitted, jarsigner may update the input archive in place. In a release pipeline, using a separate output file preserves the original artifact for comparison and recovery.

jarsigner will prompt for required passwords if not provided via options. Avoid putting production passwords directly on the command line or in logs.

### Where Are Signatures Stored in a JAR?

jarsigner creates or updates metadata in META-INF, typically including:

- MANIFEST.MF: contains digests of entries.
- .SF file: contains digests of the manifest or sections.
- Signature block files such as .RSA, .DSA, or .EC: contain the signature and signer certificate information.

Filenames depend on the signature file name and signing algorithm. You can inspect archive contents:

~~~bash
jar --list --file app-signed.jar
~~~

The signature protects the signed entries. If an entry's content is modified after signing, verification will fail. If a file is added after signing, the new file may remain unsigned. Therefore, finish packaging, resources, and metadata before signing; signing should be the final step of the artifact pipeline.

## 9. Verifying JAR Signatures

Basic command:

~~~bash
jarsigner -verify app-signed.jar
~~~

View details and signer certificates:

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

Options:

- -verify: verify the signature.
- -verbose: display detailed output.
- -certs: display certificates when used with -verbose and -verify.
- -keystore: specify the keystore used during verification.
- -strict: treat warnings as errors and return an appropriate error status.

In CI, you can use:

~~~bash
jarsigner -verify -verbose -certs -strict app-signed.jar
~~~

Only enable -strict after the truststore, certificate chain, and timestamp are properly configured for the build/verify environment. When using a self-signed certificate in a lab, verification may emit a warning that the certificate is not trusted even though the content signature is valid.

### Two Concepts to Distinguish

**Signature integrity** answers: does the JAR content match the signature?

**Signer trust** answers: can the certificate build a trusted path to a trust anchor accepted by the verifier?

A JAR can have a cryptographically matching signature while its signer certificate is not trusted by the truststore. Conversely, a trusted certificate cannot rescue a JAR that was modified after signing.

Read all jarsigner warnings and errors. Do not look only at a single "jar verified" line and ignore warnings about the chain, timestamp, expired certificate, or unsigned entries.

## 10. Timestamping When Signing JARs

A timestamp proves that a signature existed at a point in time attested by a Timestamping Authority (TSA).

Example:

~~~bash
jarsigner \
    -keystore release.p12 \
    -storetype PKCS12 \
    -digestalg SHA-256 \
    -sigalg SHA256withRSA \
    -tsa https://tsa.example.com \
    -signedjar app-signed.jar \
    app.jar \
    release-2026
~~~

The TSA URL in the example is an illustrative address; replace it with a TSA accepted by your organization or publisher.

Some timestamp options:

| Option | Meaning |
|---|---|
| -tsa | URL of the Timestamping Authority |
| -tsacert | Alias of the TSA certificate in the keystore |
| -tsapolicyid | Policy OID requested from the TSA |
| -tsadigestalg | Digest algorithm for the timestamp request |

Timestamps are useful when the signer certificate has an expiration date. If a signature is validly timestamped while the certificate is still valid, verifiers can evaluate the signing time according to the timestamp and corresponding certificate policy.

A timestamp does not extend a certificate's validity period, replace a trust chain, or turn an invalid signature into a valid one. The TSA certificate also needs to be verified and trusted according to policy.

Without a timestamp, verifying a signature after the signer certificate expires may trigger warnings or fail to meet system policy.

## 11. Choosing Digest and Signature Algorithms

jarsigner allows selecting algorithms:

~~~bash
-digestalg SHA-256
-sigalg SHA256withRSA
~~~

The digest algorithm computes hashes of the content. The signature algorithm uses the private key to sign the digest data or corresponding structure.

Common choices depending on policy:

- SHA-256 or stronger for digests.
- SHA256withRSA for RSA keys.
- SHA256withECDSA for appropriate EC keys.
- Algorithms and key sizes must be compatible with the JDK, CA, verifier, and security policy.

Do not use MD5 or SHA-1 for new release signatures. If legacy JARs use weak algorithms, check compatibility and plan to re-sign them with modern algorithms.

Do not choose a signature algorithm out of habit alone. Consider the certificate's public key, supported providers, cryptographic regulations, and recipient systems.

## 12. Renaming Aliases, Changing Passwords, and Migrating Keystores

Managing aliases and passwords are separate operations.

### Renaming an Alias

~~~bash
keytool -changealias \
    -alias release-old \
    -destalias release-2026 \
    -keystore release.p12 \
    -storetype PKCS12
~~~

Renaming an alias only changes the entry name. It does not generate a new key pair and does not alter the certificate or private key.

After renaming an alias, update signing pipelines and scripts to use the new alias name. Previously signed JARs still contain the old signatures; renaming an alias does not change signatures inside existing archives.

### Changing the Password of a Private Key Entry

~~~bash
keytool -keypasswd \
    -alias release-2026 \
    -keystore release.p12 \
    -storetype PKCS12
~~~

Depending on the provider, this operation may not be supported or may have specific constraints for PKCS12. Check the keystore type and enter the old/new passwords as prompted.

### Changing the Keystore Password

~~~bash
keytool -storepasswd \
    -keystore release.p12 \
    -storetype PKCS12
~~~

This command changes the password protecting the keystore. It does not change key pairs or certificates.

### Converting JKS to PKCS12

~~~bash
keytool -importkeystore \
    -srckeystore legacy.jks \
    -srcstoretype JKS \
    -destkeystore release.p12 \
    -deststoretype PKCS12
~~~

After converting:

1. List entries in the destination keystore.
2. Check aliases and entry types.
3. Verify the certificate chain.
4. Test accessing the private key with a test signing workflow.
5. Confirm that applications and pipelines can read the new format.
6. Keep a backup of the source keystore until verification is complete and retention policy allows removal.

Do not delete the source keystore immediately after importing without thoroughly verifying entries and recoverability.

## 13. Signing Key Rotation

Signing keys should not be used indefinitely. Rotation may be necessary when:

- The certificate is nearing expiration.
- The algorithm or key size no longer meets policy.
- Key-management personnel or providers change.
- The private key may have been compromised.
- The organization changes its CA or release process.
- Environments or products need to be separated.

Rotation workflow:

1. Generate a new key pair with a distinct alias and identifier.
2. Create a CSR and request a new certificate.
3. Verify Subject, Issuer, validity, fingerprint, and extensions.
4. Update the signing pipeline to the new alias.
5. Sign new release artifacts with the new key.
6. Verify that users and target systems accept the new certificate.
7. Retain the old certificate to verify previously released artifacts per policy.
8. Revoke the old certificate if an incident occurs or policy requires it.
9. Retire the old private key after the transition period completes.
10. Record the timestamp, approver, and related artifacts.

Do not delete the old certificate simply because you renamed an alias or created a new key pair. Users may need to verify artifacts signed with the old certificate in the future.

If a private key is compromised, simple rotation is not enough. Assess the scope of affected artifacts, revoke the certificate through the CA process, issue an advisory, and re-sign necessary artifacts.

## 14. Keystore Backup and Recovery

A private key generally cannot be reconstructed from a public certificate. If the private key is lost, you cannot continue signing with the old identity.

Backups should include:

- An encrypted keystore with protected access permissions.
- Passwords or unlock mechanisms stored in a separate secret manager.
- Backup copies in a controlled location.
- A tested recovery procedure.
- Metadata about aliases, certificate chains, algorithms, and expiration dates.
- A process defining who is authorized to recover or use the key.

Do not store passwords in the same directory as the keystore in an unprotected manner. Do not commit keystores or secret files to Git.

Backups do not replace access control. An unprotected copy of a private key is also a copy that can be stolen.

For critical keys, consider an HSM or key management service so the private key does not need to be exported as a regular file.

## 15. Managing Keys in an HSM or PKCS11

In environments with high security requirements, private keys may reside in an HSM or hardware token. Applications call a provider to use the key; the private key does not need to leave the device.

keytool and jarsigner support providers such as SunPKCS11 via provider configuration:

~~~bash
keytool -list \
    -keystore NONE \
    -storetype PKCS11 \
    -addprovider SunPKCS11 \
    -providerarg pkcs11.cfg
~~~

Exact syntax and configuration depend on the JDK, provider, driver, and device. Some systems require a token PIN or protected authentication path.

jarsigner also has provider options such as -addprovider, -providerArg, -providerClass, and -providerPath. Check the help output for your specific JDK and the HSM vendor's documentation.

Benefits of an HSM:

- Reduces the need to export private keys to files.
- Can enforce key-usage policies inside the device.
- Supports auditing and access control.
- Can require multi-factor authentication or approvals for signing operations.

An HSM does not automatically secure the entire release process. The pipeline, token access permissions, firmware, backups, and approval workflows still need to be managed.

## 16. Protecting Keys in CI/CD

Signing keys are sensitive assets in the release process. If a private key is exposed, an attacker can create artifacts carrying the organization's signature.

Practices:

- Use a secret manager or organizational key management system.
- Never store passwords in source code, build files, or logs.
- Restrict jobs with signing permissions to approved release pipelines only.
- Use ephemeral runners or a controlled signing environment.
- Separate development, staging, and production keys.
- Restrict who has permission to read or use the keystore.
- Record audit logs for every signing operation.
- Inspect artifacts and dependencies before signing.
- Sign last, after all content is finalized.
- Store artifact checksums, versions, and provenance alongside signing results.
- Rotate keys on schedule and upon incidents.

If a password must be passed to a process in CI, use a platform-protected secret injection mechanism and avoid printing the value to logs. Evaluate process arguments, environment variables, temporary files, and runner permissions; no single password-passing method fits every system.

Never allow pull requests from untrusted sources to run jobs with access to production signing keys.

## 17. Java 17+ Example: Building a JAR and Preparing for Signing

This example creates a small application that can be packaged into a JAR. The Java part compiles and runs independently; the keytool/jarsigner commands that follow illustrate the artifact signing workflow.

Structure:

~~~text
jar-signing-demo/
├── src/
│   └── com/
│       └── example/
│           └── Main.java
└── build/
    ├── classes/
    ├── app.jar
    ├── release.p12
    └── app-signed.jar
~~~

### Main.java

~~~java
package com.example;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String version = args.length == 0 ? "development" : args[0];
        System.out.println("Release " + version + " ready.");
    }
}
~~~

### Compiling

From the jar-signing-demo root directory:

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/com/example/Main.java
~~~

### Running the Class

~~~bash
java -cp build/classes com.example.Main 1.0.0
~~~

Output:

~~~text
Release 1.0.0 ready.
~~~

### Creating a JAR with Main-Class

~~~bash
jar --create \
    --file build/app.jar \
    --main-class com.example.Main \
    -C build/classes .
~~~

Inspect the manifest and contents:

~~~bash
jar --list --file build/app.jar
jar --describe-module --file build/app.jar
~~~

This JAR is an automatic module if placed on the module path without a module descriptor. Since this example only needs an executable JAR on the classpath, module-info.java is not needed.

### Generating a Key Pair for the Lab

~~~bash
keytool -genkeypair \
    -alias demo-release \
    -keyalg RSA \
    -keysize 2048 \
    -sigalg SHA256withRSA \
    -dname "CN=Demo Release Signer, OU=Training, O=Example, C=VN" \
    -validity 30 \
    -keystore build/demo-release.p12 \
    -storetype PKCS12
~~~

In the lab, keytool will prompt for a password. A self-signed certificate is for demonstration only; recipients can verify the signature, but they will not automatically trust the signer's identity.

### Signing the JAR

~~~bash
jarsigner \
    -keystore build/demo-release.p12 \
    -storetype PKCS12 \
    -digestalg SHA-256 \
    -sigalg SHA256withRSA \
    -signedjar build/app-signed.jar \
    build/app.jar \
    demo-release
~~~

### Verifying the Signature

~~~bash
jarsigner -verify -verbose -certs build/app-signed.jar
~~~

In the lab, warnings may appear regarding a self-signed certificate or an untrusted chain. That is a different situation from a signature content error. Read the full output to distinguish them.

### Viewing the Signer Certificate

~~~bash
keytool -printcert -jarfile build/app-signed.jar
~~~

### Running the Signed JAR

~~~bash
java -jar build/app-signed.jar 1.0.0
~~~

Application output:

~~~text
Release 1.0.0 ready.
~~~

Being able to run the JAR does not replace signature verification. Perform verification separately in the pipeline or before deployment.

## 18. Common Issues in Signing Key Management

### Alias Does Not Exist

jarsigner cannot find the alias in the keystore. Check:

~~~bash
keytool -list -keystore release.p12 -storetype PKCS12
~~~

Use the exact alias and the correct keystore file.

### Unable to Open Keystore

Check the password, storetype, provider, and path. JKS and PKCS12 cannot be interchanged simply by changing the file extension.

### Certificate Reply Does Not Match Private Key

The CA-issued certificate must contain the public key corresponding to the private key in the alias. Generate the CSR from the exact alias and do not generate a new key pair between sending the CSR and importing the reply.

### Missing Certificate Chain

Import intermediate/root certificates according to the CA process or supply the full chain. Check the Certificate chain length and Issuer after importing.

### jarsigner Reports No Private Key

The alias may only be a trustedCertEntry, or the keystore does not contain the corresponding private key. Signing a JAR requires a PrivateKeyEntry with a usable private key.

### Invalid Signature After Packaging

The artifact may have been modified after signing. Complete building, compressing, adding resources, and updating the manifest before signing. If the content changes, create a new artifact and sign it again.

### Untrusted Certificate

The signature may match, but the certificate chain does not terminate at an accepted trust anchor. Check the CA, truststore, and policies of the verification environment. Do not import an unfamiliar certificate just to silence warnings.

### Expired Certificate or Missing Timestamp

Check validity and the timestamp token. Use a trusted TSA when required by release policy. The timestamp must be verified; merely having a timestamp field is not sufficient to prove signature validity.

### Rejected Algorithm

The JDK may reject weak algorithms under its security policy. Choose a supported digest/signature algorithm permitted by policy; do not weaken security policies just to make legacy artifacts pass verification.

### -strict Causes Build Failure

-strict treats warnings as errors. Read the specific warnings and fix the trust chain, timestamp, unsigned entries, or certificate issues. Do not remove -strict without understanding the cause if CI requires strict verification.

## 19. Signed Release Workflow

A JAR signing pipeline can follow this sequence:

~~~text
Source
  |
  v
Compile and test
  |
  v
Package unsigned JAR
  |
  v
Inspect artifact and dependencies
  |
  v
Authorize signing job
  |
  v
Use protected private key
  |
  v
Sign JAR and request timestamp
  |
  v
Verify signature, certificate and timestamp
  |
  v
Publish immutable signed artifact
~~~

Control points:

1. Build only from approved commits or releases.
2. Inspect dependencies and contents before signing.
3. Only the signing job has access to the private key.
4. Do not export the private key from an HSM if prohibited by policy.
5. Sign the final artifact and do not modify it after signing.
6. Verify the signature immediately after signing.
7. Check the certificate chain and timestamp against trust policy.
8. Store audit logs, checksums, versions, and signer identity.
9. Publish the exact artifact that was verified.
10. Keep rotation and incident response procedures ready.

## 20. Signing Key Management Checklist

- [ ] Each environment or product has its own key according to policy.
- [ ] Private keys are generated in a controlled environment.
- [ ] Algorithms and key sizes meet current policy.
- [ ] Aliases and Subjects are named clearly.
- [ ] CSRs are generated from the correct key pair.
- [ ] Certificate replies and chains have been verified.
- [ ] Keystores use a supported format, preferring PKCS12 when appropriate.
- [ ] Passwords and private keys are not stored in repositories or logs.
- [ ] Backups are protected and recovery has been tested.
- [ ] Signing jobs have the minimum required permissions.
- [ ] Artifacts are completely packaged before signing.
- [ ] Timestamps are added when required by policy.
- [ ] jarsigner verification succeeds according to trust policy.
- [ ] Warnings about self-signed certificates, chains, expiry, and unsigned entries are addressed.
- [ ] Certificates and keys have a rotation schedule.
- [ ] A revocation procedure exists in case a private key is compromised.
- [ ] Signed artifacts are stored immutably with checksums and provenance.

## 21. Essential keytool and jarsigner Commands

~~~bash
# Generate a key pair
keytool -genkeypair -alias release-2026 \
    -keyalg RSA -keysize 3072 \
    -keystore release.p12 -storetype PKCS12

# Create a certificate request
keytool -certreq -alias release-2026 \
    -keystore release.p12 -storetype PKCS12 \
    -file release-2026.csr

# Import a CA-issued certificate reply
keytool -importcert -alias release-2026 \
    -file release-reply.pem \
    -keystore release.p12 -storetype PKCS12

# Inspect key and certificate chain
keytool -list -v -alias release-2026 \
    -keystore release.p12 -storetype PKCS12

# Export the public certificate
keytool -exportcert -rfc -alias release-2026 \
    -keystore release.p12 -storetype PKCS12 \
    -file release-2026.pem

# Sign the final JAR
jarsigner -keystore release.p12 -storetype PKCS12 \
    -digestalg SHA-256 -sigalg SHA256withRSA \
    -signedjar app-signed.jar app.jar release-2026

# Verify signature and show signer certificate
jarsigner -verify -verbose -certs app-signed.jar

# Apply strict verification policy
jarsigner -verify -verbose -certs -strict app-signed.jar

# Rename an alias
keytool -changealias -alias old-name -destalias new-name \
    -keystore release.p12 -storetype PKCS12

# Convert a JKS keystore to PKCS12
keytool -importkeystore \
    -srckeystore legacy.jks -srcstoretype JKS \
    -destkeystore release.p12 -deststoretype PKCS12
~~~

Signing key management is about managing the lifecycle of a release identity, not just running a JAR signing command. When private keys are protected, certificate chains are verified, artifacts are signed as the final step, and signatures are verified against trust policy, teams can release JARs whose origin and integrity can be verified across versions.

## References

- [The keytool Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html)
- [The jarsigner Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- [Java Security Developer's Guide — PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/24/security/java-pki-programmers-guide.html)
- [JAR File Specification — Signing and Verification](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html)
