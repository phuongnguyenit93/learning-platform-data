# Signing JARs with jarsigner

**jarsigner** is a command-line tool included with the JDK for digitally signing and verifying signatures of Java Archives (JARs). When signing, the tool uses the publisher's private key to generate a digital signature for the entries in the JAR. The certificate corresponding to the public key and the signer's certificate chain are stored alongside the signature inside the JAR file.

Signing a JAR allows recipients to verify two important properties:

- **Integrity**: the signed entries have not been modified since they were signed.
- **Authenticity**: the signature was created with the private key corresponding to the public key in the signer's certificate.

JAR signing does not encrypt the contents, hide classes or resources, prove that a program is safe, or automatically grant permissions for the application to run. Recipients still need to evaluate the certificate, signer identity, download source, and their own security policies.

## 1. General JAR Signing Workflow

A typical release workflow includes the following steps:

1. Compile and package the application into a JAR.
2. Prepare the signer's key pair and certificate in a keystore.
3. Use jarsigner to sign the JAR with the alias containing the private key.
4. Generate a timestamp via a Time Stamping Authority (TSA) when required by the release process.
5. Verify the signature and entries using jarsigner -verify.
6. Inspect the certificate chain, signer identity, timestamp, and warnings.
7. Release the exact artifact that was signed and verified.

Overview diagram:

~~~text
Java source
    |
    v
javac / jar
    |
    v
app.jar (unsigned)
    |
    +---- keystore: private key + signer certificate chain
    |
    v
jarsigner
    |
    +---- META-INF/MANIFEST.MF
    +---- META-INF/ACME.SF
    +---- META-INF/ACME.RSA
    |
    v
app-signed.jar
    |
    v
jarsigner -verify
    |
    +---- signature integrity
    +---- certificate / timestamp diagnostics
    |
    v
release artifact
~~~

jarsigner can sign JARs created by the jar tool as well as ZIP archives. When signing a ZIP without an existing manifest, the tool creates META-INF/MANIFEST.MF to store entry digests.

## 2. Preparing the Keystore and Signing Key

To sign a JAR, you need a public/private key pair along with a certificate that authenticates the public key. The private key is used to generate the signature; the certificate and chain are included in the signature block so the recipient can verify it.

In Java, keytool manages keystores. Since JDK 9, the default keystore type is typically PKCS12. You should explicitly specify the store type in scripts to avoid depending on machine-level configuration.

### Creating a test keystore

Example of creating an RSA key pair for learning and internal testing:

~~~bash
keytool -genkeypair \
  -alias acme \
  -keyalg RSA \
  -keysize 3072 \
  -validity 3650 \
  -dname "CN=Acme Demo, O=Acme, C=VN" \
  -keystore signing.p12 \
  -storetype PKCS12
~~~

keytool will prompt for the keystore password and may ask for a separate password for the private key. Never hardcode real passwords directly in source code or repositories.

Explanation:

- -genkeypair generates a public/private key pair and a certificate.
- -alias acme names the entry so jarsigner can locate the right private key.
- -keyalg RSA selects the RSA key algorithm.
- -keysize 3072 sets the key size.
- -validity 3650 sets the validity period of the generated self-signed certificate, in days.
- -dname sets the Distinguished Name for the certificate.
- -keystore signing.p12 specifies the keystore file.
- -storetype PKCS12 selects the storage format.

The self-signed certificate in this example is only suitable for labs, testing, and verifying the workflow. It does not automatically become a publisher certificate trusted by systems or users.

### Inspecting the alias

~~~bash
keytool -list -v \
  -keystore signing.p12 \
  -storetype PKCS12 \
  -alias acme
~~~

Check the following details:

- Alias name is acme.
- Entry type is PrivateKeyEntry.
- Certificate has the expected Subject and Issuer.
- Public key algorithm and key size are correct.
- Validity dates are appropriate.
- Certificate chain contains all required components.

A PrivateKeyEntry is required for signing. A trustedCertEntry only contains a public certificate and does not have a private key to create signatures.

## 3. Using a CA-Issued Code-Signing Certificate

In real release environments, organizations typically use a code-signing certificate issued by a CA under an appropriate policy. Typical workflow:

1. Generate a private key in a keystore or HSM.
2. Create a certificate signing request (CSR).
3. Submit the CSR to a code-signing CA.
4. Receive the CA-signed certificate and certificate chain.
5. Import the certificate reply into the same alias where the private key was generated.
6. Verify the chain and certificate usage purpose before signing.

Generate a CSR:

~~~bash
keytool -certreq \
  -alias acme \
  -file acme-signing.csr \
  -keystore signing.p12 \
  -storetype PKCS12
~~~

After the CA issues the certificate reply, import it into the alias that already holds the private key:

~~~bash
keytool -importcert \
  -alias acme \
  -file acme-code-signing-chain.p7b \
  -keystore signing.p12 \
  -storetype PKCS12
~~~

The file name and format of the certificate reply depend on the CA. When importing a certificate reply for an alias with a private key, keytool associates the new certificate chain with the existing private key.

Do not create a new trusted certificate alias and mistake it for the signing key. The alias used for signing must contain the private key along with its corresponding certificate chain.

A code-signing certificate needs appropriate KeyUsage and ExtendedKeyUsage extensions. If the certificate is not permitted for code signing, jarsigner may emit warnings about badKeyUsage or badExtendedKeyUsage.

## 4. Packaging the Application into a JAR Before Signing

You should sign the final artifact after compiling, packaging resources, and finalizing the manifest. Any content modification after signing can invalidate entry digests.

Java 17 application example:

~~~text
project/
  src/
    com/acme/Main.java
  out/
  app.jar
~~~

File src/com/acme/Main.java:

~~~java
package com.acme;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from signed JAR");
    }
}
~~~

Compile:

~~~bash
javac --release 17 -d out src/com/acme/Main.java
~~~

Package as an executable JAR:

~~~bash
jar --create \
  --file app.jar \
  --main-class com.acme.Main \
  -C out .
~~~

Inspect the archive contents:

~~~bash
jar --list --file app.jar
~~~

You can run the unsigned build to test the application before signing:

~~~bash
java -jar app.jar
~~~

Stdout:

~~~text
Hello from signed JAR
~~~

This is the program verification step. The signature is created afterward to protect the integrity and authenticate the publisher of the artifact.

## 5. Signing a JAR with jarsigner

Basic syntax:

~~~bash
jarsigner [options] jar-file alias
~~~

Example of signing app.jar using the acme alias in signing.p12 and writing the output to a separate file:

~~~bash
jarsigner \
  -keystore signing.p12 \
  -storetype PKCS12 \
  -signedjar app-signed.jar \
  app.jar \
  acme
~~~

jarsigner prompts for the keystore password and private key password if needed. If passwords are not provided on the command line, the tool asks interactively.

Argument meanings:

- -keystore specifies where the private key and certificate are stored.
- -storetype specifies the keystore type.
- -signedjar sets the name of the generated signed JAR.
- app.jar is the input JAR.
- acme is the alias containing the private key used for signing.

If -signedjar is omitted, jarsigner overwrites the input JAR with the signed version. In release pipelines, you should write to a separate output file so you can compare the unsigned and signed artifacts and avoid accidental overwrites.

If the keystore is the default .keystore file in the user's home directory, jarsigner can find it without -keystore. However, build/release scripts should explicitly specify the keystore so results are reproducible and controlled.

## 6. How Is a JAR Signed?

When signing, jarsigner adds files under the META-INF directory. For an RSA signer with alias acme, the files typically look like:

~~~text
META-INF/
  MANIFEST.MF
  ACME.SF
  ACME.RSA
~~~

The default signature file name takes up to the first eight characters of the alias, converted to uppercase. The signature block has an extension depending on the key algorithm, such as .RSA, .DSA, or .EC.

The three components serve different roles:

### MANIFEST.MF

The manifest contains metadata and digests of the entries in the JAR. Digests are computed over the binary contents of each signed entry.

### Signature file (.SF)

The .SF file contains digests of the corresponding sections in the manifest. By default, it also includes a header containing a digest of the entire manifest to optimize verification.

### Signature block (.RSA, .DSA, or .EC)

The signature block contains the digital signature of the .SF file and the certificate or certificate chain authenticating the public key corresponding to the private key that signed it.

Conceptual relationship:

~~~text
Entry bytes
    |
    v
Entry digest
    |
    v
MANIFEST.MF
    |
    v
Digest of manifest sections
    |
    v
ACME.SF
    |
    v
Private-key signature
    |
    v
ACME.RSA + signer certificate chain
~~~

During verification, jarsigner checks the signature of the .SF file, compares digests between the .SF file and the manifest, and recomputes the digests of the entries to compare them. If the contents of a signed entry were altered, the check fails.

Signing does not encrypt entries. Recipients can still open the JAR and read classes/resources like a normal ZIP archive.

## 7. Verifying a Signed JAR

Use the -verify option:

~~~bash
jarsigner -verify app-signed.jar
~~~

When the signature and entry contents pass verification, jarsigner may display:

~~~text
jar verified.
~~~

To view per-entry details:

~~~bash
jarsigner -verify -verbose app-signed.jar
~~~

To view the signer's certificate information:

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

Common flags in verbose output:

| Flag | Meaning |
|---|---|
| s | Entry signature was verified |
| m | Entry is listed in the manifest |
| k | At least one matching certificate was found in the checked keystore |

Verbose output can display the signer DN, certificate chain, digest algorithm, signature algorithm, and timestamp.

### Verifying a specific signer

When you need to confirm that a JAR was signed by the expected alias, you can specify the keystore and alias at the end of the verify command:

~~~bash
jarsigner -verify -verbose -certs \
  -keystore trusted-signers.p12 \
  -storetype PKCS12 \
  app-signed.jar \
  acme
~~~

Providing the alias after the JAR name requires the certificate used to verify the entries to match the corresponding alias in the keystore. This is useful when a pipeline only accepts artifacts published by a specific signer.

Do not confuse a cryptographically valid signature with the signer's identity being trusted by your organization. Always verify the certificate chain and fingerprint through a trusted source.

## 8. A Valid Signature Is Different from a Trusted Signer

A JAR can have a cryptographically valid signature while the signer's certificate is self-signed or its chain does not lead to a trusted CA.

Distinguish three questions:

1. **Integrity**: were the entries modified after signing?
2. **Signature authenticity**: does the signature match the public key in the certificate?
3. **Signer trust**: does the certificate accurately authenticate the publisher's identity and is it accepted by your trust policy?

For example, a lab using a self-signed certificate can pass signature and digest checks while still producing signerSelfSigned or chainNotValidated warnings. That does not turn a test certificate into a CA-verified publisher identity.

When evaluating a release JAR:

- Verify the certificate chain.
- Check Subject, Issuer, validity, and KeyUsage/ExtendedKeyUsage.
- Check the certificate fingerprint against information published by the vendor via an independent channel.
- Inspect timestamps and warnings.
- Compare the signer against the list of signers approved by your organization.
- Confirm the artifact was downloaded from an official release source.

jarsigner can use the default keystore or a specified keystore to provide additional certificate information. With detailed verification, -certs displays the signer's certificate. Do not treat a single `jar verified` line as sole proof that the publisher has been verified according to organizational policy.

## 9. Timestamps for JAR Signatures

A timestamp records the time a signature was created through a Time Stamping Authority (TSA). The timestamp token is stored alongside the signature block.

Generate a timestamp using a TSA URL:

~~~bash
jarsigner \
  -keystore signing.p12 \
  -storetype PKCS12 \
  -tsa https://tsa.example.com \
  -signedjar app-signed.jar \
  app.jar \
  acme
~~~

The URL in the example is illustrative. In production releases, use the TSA endpoint provided by your CA or signing service provider.

You can use -tsacert alias if the TSA certificate is stored in the keystore and has a Subject Information Access extension containing the TSA URL:

~~~bash
jarsigner -tsacert tsa-certificate ...
~~~

Related options:

| Option | Purpose |
|---|---|
| -tsa URL | Specifies the TSA URL |
| -tsacert alias | Obtains TSA information from a certificate in the keystore |
| -tsapolicyid OID | Sends a policy identifier to the TSA |
| -tsadigestalg algorithm | Selects the digest algorithm for the timestamp request |

On JDK 26, the default digest for timestamp requests is SHA-384 if -tsadigestalg is not specified.

### Why are timestamps useful?

If the JAR-signing certificate expires after the release date, a valid timestamp helps establish that the JAR was signed while the certificate was still valid. Whether a signature is accepted after certificate expiration still depends on verification rules, certificate status, the timestamp chain, and the runtime's algorithm policies.

A timestamp does not make a revoked certificate trusted again and cannot rescue a signature that uses a disabled algorithm.

Without a timestamp, jarsigner may emit the informational warning noTimestamp. For long-lived software distributions, use a trusted TSA according to your release policy.

## 10. Digest and Signature Algorithms

JAR signing uses two types of algorithms:

- **Digest algorithm** computes hashes of entries and manifest sections.
- **Signature algorithm** uses the private key to sign the digest data or corresponding signature structure.

In JDK 26, the default digest algorithm for jarsigner is SHA-384 if -digestalg is not specified. The default signature algorithm depends on the private key's type and size.

You can explicitly specify algorithms when needed:

~~~bash
jarsigner \
  -digestalg SHA-384 \
  -sigalg SHA384withRSA \
  -keystore signing.p12 \
  -storetype PKCS12 \
  -signedjar app-signed.jar \
  app.jar \
  acme
~~~

The signature algorithm must be compatible with the private key and the installed security providers.

The JDK provides security properties such as jdk.jar.disabledAlgorithms and jdk.security.legacyAlgorithms to control disabled or legacy algorithms. A JAR using a disabled algorithm may be treated as unsigned; a legacy algorithm may produce warnings.

Do not use SHA-1 or weak algorithms for new artifacts. Nor should you pin an algorithm without testing compatibility with target JDK runtimes. Defaults may change across releases to strengthen security.

## 11. Multiple Signatures and Multiple Signers

A JAR can be signed by multiple signers. Running jarsigner multiple times with different aliases adds a pair of signature file and signature block for each signer.

Example:

~~~bash
jarsigner -keystore release-a.p12 -signedjar stage-a.jar app.jar releaseA
jarsigner -keystore release-b.p12 -signedjar app-final.jar stage-a.jar releaseB
~~~

The final JAR can contain multiple signature pairs in META-INF. During verification, jarsigner checks the corresponding signatures.

Multiple signatures are useful when:

- Two organizations jointly approve an artifact.
- A publisher and a distributor need to sign independently.
- A release process requires signatures from multiple roles.

A new signer's signature does not remove previous signatures. However, all signers and certificate chains must be evaluated according to release policy.

## 12. Commonly Used jarsigner Options

| Option | Meaning |
|---|---|
| -keystore | Selects the keystore containing the signing key or certificates used during verify |
| -storetype | Selects the keystore type such as PKCS12 or JKS |
| -signedjar | Sets the output signed JAR file name |
| -verify | Verifies the JAR signature |
| -verbose | Displays detailed signing/verification output |
| -certs | Displays certificate details during verbose verification |
| -sigfile | Sets the base name for the .SF and signature block files |
| -digestalg | Selects the digest algorithm for entries |
| -sigalg | Selects the signature algorithm compatible with the private key |
| -tsa | Generates a timestamp using a TSA URL |
| -tsacert | Uses a TSA certificate from the keystore |
| -revCheck | Enables certificate revocation checking via OCSP/CRL |
| -strict | Makes severe warnings affect the exit code |
| -certchain | Supplies the certificate chain when the private-key entry lacks a full chain |
| -storepass | Supplies the keystore password |
| -keypass | Supplies the private key password |

Some options such as -storepass and -keypass are only needed for signing; basic signature verification does not require a keystore password.

### Passwords and CI/CD

Never put real passwords on the command line or in committed script files. JDK 26 supports environment variable and file password modifiers:

~~~bash
jarsigner \
  -storepass:env SIGNING_STORE_PASSWORD \
  -keypass:env SIGNING_KEY_PASSWORD \
  -keystore signing.p12 \
  -storetype PKCS12 \
  app.jar \
  acme
~~~

Only use environment variables provisioned and protected by your CI secret manager. For manual operations, letting jarsigner prompt interactively is usually safer than storing passwords in shell history.

### Signing with an HSM or PKCS#11

If the private key is held in a hardware token or HSM, you do not need to export the private key to a file. Once a PKCS#11 provider is configured, jarsigner can access the token using:

~~~bash
jarsigner \
  -keystore NONE \
  -storetype PKCS11 \
  -signedjar app-signed.jar \
  app.jar \
  acme
~~~

The token may require a PIN or a protected authentication path. Configure the provider, token, and access permissions according to the device documentation.

## 13. -strict and Handling Warnings in Pipelines

By default, jarsigner may return exit code 0 when signing or verification succeeds even with severe warnings. When -strict is added, severe warnings are reflected in the exit code.

Example:

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

Common severe warnings:

| Warning | Meaning |
|---|---|
| hasExpiredCert | Signer certificate has expired |
| notYetValidCert | Signer certificate is not yet valid |
| chainNotValidated | Certificate chain could not be validated |
| signerSelfSigned | Signer certificate is self-signed |
| disabledAlg | Algorithm is disabled by security policy |
| badKeyUsage | KeyUsage does not allow code signing |
| badExtendedKeyUsage | ExtendedKeyUsage does not allow code signing |
| hasUnsignedEntry | JAR contains an entry that has not been integrity-checked |
| notSignedByAlias | Entry was signed by an alias other than the requested alias |
| aliasNotInStore | Signer has no matching alias in the specified keystore |

Informational warnings can include:

- noTimestamp: the signature has no timestamp.
- legacyAlg: an algorithm considered legacy is used.
- hasExpiringCert: the certificate is expiring soon.
- extraAttributesDetected: POSIX permissions or symlink attributes are present and not protected by the signature.

Not all warnings carry the same severity. Read the warning details and apply your release policy. In CI, it is generally best to use -strict and require the certificate chain, signer, algorithms, timestamp, and entry coverage to satisfy policy.

Note: -strict makes severe warnings affect the exit status; informational warnings may still not cause the command to fail.

## 14. What Happens If a JAR Is Modified After Signing?

The signature protects the digests of the signed entries. If an entry's contents are modified after signing, the recomputed digest will not match and verification will fail.

Example:

1. Sign app.jar into app-signed.jar.
2. Open the archive and modify com/acme/Main.class.
3. Run jarsigner -verify.
4. Verification detects that the entry was modified.

If a new entry is added after signing, the new entry may lack a corresponding digest in the signer's signature. The JAR may produce a hasUnsignedEntry warning because the new entry has not been integrity-checked.

Therefore, a release process must:

- Complete compilation and packaging before signing.
- Never modify the manifest or resources after signing.
- Never inject new dependencies or classes into a signed JAR.
- Run verification after signing.
- Release the exact verified output file.
- If content changes are needed, rebuild the JAR and sign it again from scratch.

Signatures do not protect filesystem attributes such as POSIX permissions or symlink metadata in all cases. jarsigner may warn when it detects these attributes.

## 15. Complete Hands-On Example for Java 17+

The following example creates an executable JAR, signs it with a test certificate, verifies it, and runs the program. The self-signed certificate is only for learning the workflow, not for distributing software to users.

Directory structure:

~~~text
jar-signing-demo/
  src/
    com/acme/Main.java
  out/
  signing.p12
  app.jar
  app-signed.jar
~~~

### Step 1: Create the source file

File src/com/acme/Main.java:

~~~java
package com.acme;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from signed JAR");
    }
}
~~~

### Step 2: Compile

~~~bash
javac --release 17 -d out src/com/acme/Main.java
~~~

### Step 3: Create the JAR

~~~bash
jar --create --file app.jar --main-class com.acme.Main -C out .
~~~

### Step 4: Generate a signing key

~~~bash
keytool -genkeypair -alias acme -keyalg RSA -keysize 3072 -validity 3650 -dname "CN=Acme Demo, O=Acme, C=VN" -keystore signing.p12 -storetype PKCS12
~~~

Enter the password when prompted and inspect the alias:

~~~bash
keytool -list -v -keystore signing.p12 -storetype PKCS12 -alias acme
~~~

### Step 5: Sign to a new file

~~~bash
jarsigner -keystore signing.p12 -storetype PKCS12 -signedjar app-signed.jar app.jar acme
~~~

### Step 6: Verify the signature

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

With a self-signed certificate, the output may contain warnings about a self-signed signer, chain, or timestamp. This is expected for a lab example. Do not use a self-signed certificate as proof of publisher identity.

### Step 7: Run the signed JAR

~~~bash
java -jar app-signed.jar
~~~

Stdout:

~~~text
Hello from signed JAR
~~~

The program still runs like a regular executable JAR. Signing adds integrity and authenticity verification; it does not alter the program's logic.

## 16. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| jarsigner cannot find alias | Wrong alias or keystore does not contain a private key | Use keytool -list -v to check the alias and entry type |
| Cannot recover key | Wrong key password or private key is inaccessible | Check the key password, provider, and token |
| Keystore password was incorrect | Wrong password or wrong store type | Check the password and PKCS12/JKS |
| JAR verification failed | Entry was modified or signature metadata is invalid | Rebuild the JAR and re-sign |
| hasUnsignedEntry | Unsigned entry present or added after signing | Complete packaging before signing and check all entries |
| signerSelfSigned | Signer certificate is self-signed | Use a CA-issued certificate for real releases |
| chainNotValidated | Missing intermediate/root CA or untrusted chain | Check the chain and trust anchors in the verification environment |
| noTimestamp | No timestamp token present | Use a TSA approved by your organization or CA |
| disabledAlg | Signing or digest algorithm is disabled by JDK policy | Use a supported algorithm and key strength |
| badKeyUsage | Certificate does not permit code signing | Request a certificate with appropriate KeyUsage |
| badExtendedKeyUsage | EKU is not suitable for code signing | Check the certificate profile with the CA |
| Timestamp failure | TSA unreachable or invalid timestamp response | Check the TSA endpoint, network, certificate, and policy |
| Verification differs across JDKs | Different security properties or supported algorithms | Check jdk.jar.disabledAlgorithms and test on the target JDK |
| JAR reports verified but publisher is unconfirmed | Signature is valid but signer certificate is not yet trusted | Verify the fingerprint, certificate chain, and signer identity |

## 17. JAR Signing Workflow in CI/CD

A release pipeline should separate build, sign, and verify steps:

1. Build source with a pinned JDK release.
2. Run unit tests and integration tests.
3. Package the final JAR and inspect the manifest.
4. Retrieve the signing key from a protected keystore or HSM.
5. Sign the JAR using an approved alias.
6. Use a trusted TSA to generate a timestamp per policy.
7. Run jarsigner -verify -strict -verbose -certs.
8. Confirm the signer certificate, chain, timestamp, and algorithms.
9. Record the hash of the signed artifact and build provenance.
10. Release the exact verified artifact; do not modify it after signing.

Restrict private key usage permissions to the necessary release jobs. Never place signing keys or passwords in source repositories, untrusted build images, or CI logs.

If using an HSM, prefer signing directly inside the device so the private key never leaves the hardware. Manage signing permissions, audit logs, backups, and rotation according to organizational policy.

## 18. Key Takeaways

- jarsigner signs and verifies JARs using a private key and certificate in a keystore.
- The alias must point to an entry with a private key in order to sign.
- A signed JAR contains a manifest, a .SF signature file, and a signature block such as .RSA, .DSA, or .EC.
- Digests in the manifest protect entry contents; the signature block holds the signature and certificate chain.
- -signedjar writes to a separate output file, avoiding overwriting the input JAR.
- -verify checks the signature and integrity; -verbose -certs displays signer certificate details.
- A cryptographically valid signature does not mean the publisher is trusted.
- Timestamping via -tsa establishes when signing occurred and helps verification after the signer certificate expires.
- JDK 26 defaults to SHA-384 for entry digests; the default signature algorithm depends on key type and size.
- jdk.jar.disabledAlgorithms and jdk.security.legacyAlgorithms govern disabled algorithms and legacy warnings.
- -strict makes severe warnings affect the exit code; consider using it in CI.
- -revCheck enables certificate revocation checking via OCSP/CRL; this check is not enabled by default.
- Modifying an entry after signing breaks integrity; adding a new entry can trigger an unsigned-entry warning.
- JAR signing does not encrypt contents or prove a program is safe.
- Only release an artifact after verifying the signature, certificate chain, signer identity, timestamp, and warnings against policy.

## Official References

- [The jarsigner Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html)
- [The keytool Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html)
- [Java Security Standard Algorithm Names — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html)
- [JAR File Specification — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)
- [Signing JAR Files — Oracle Java Tutorials](https://docs.oracle.com/javase/tutorial/deployment/jar/signing.html)