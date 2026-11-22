# Certificate Chains in JAR Signing

When signing a JAR with `jarsigner`, the tool does more than generate a digital signature for the archive contents. The JAR also carries the signer's certificate and may include intermediate certificates so the recipient can validate the trust path. A certificate chain connects the signer's certificate to a root CA that the verifier already trusts.

It is important to distinguish three questions:

1. **Integrity:** Do the JAR contents still match the signed digests?
2. **Signature:** Can the signature be verified using the public key in the signer's certificate?
3. **Trust:** Does the signer's certificate form a valid chain to a trust anchor trusted by the recipient?

A JAR can have a cryptographically valid signature while the signer certificate is still untrusted. This guide uses JDK 17 or later and explains JAR signature structure, how to prepare a certificate chain, how to sign and verify with `jarsigner`, and common errors encountered when releasing artifacts.

## 1. What Is a Certificate Chain?

A certificate chain is the verification path from an end-entity certificate to a trusted root CA.

For a JAR signed with a CA-issued certificate, the chain typically has the following structure:

~~~text
Signer certificate (leaf / end-entity)
        |
        | signed by
        v
Intermediate CA certificate
        |
        | signed by
        v
Root CA certificate (trust anchor)
~~~

Roles in the chain:

- **Signer/leaf certificate:** The certificate bound to the public key used to verify the JAR signature. This certificate represents the organization or publisher.
- **Intermediate CA:** An intermediate CA that signs the signer's certificate or another subordinate CA. It allows the root CA to avoid signing every end-entity certificate directly.
- **Root CA:** The root CA configured by the verifier as a trust anchor. A root is typically self-signed and distributed in a trusted truststore.
- **Signer's private key:** The private key corresponding to the public key in the leaf certificate. This key is kept in a protected keystore or signing device and is never included in the JAR.

A chain may contain multiple intermediate CAs. The verifier checks each certificate's signature, issuer/subject relationship, validity period, constraints, and key usage policies. The root CA must be trusted independently; a certificate claiming to be a root does not make it automatically trustworthy.

## 2. Where Does the Certificate Chain Appear in a Signed JAR?

JAR signing uses components under the `META-INF` directory:

| Component | Role |
|---|---|
| `META-INF/MANIFEST.MF` | Contains digests of the signed entries |
| `META-INF/ALIAS.SF` | Signature file containing digests of the manifest or corresponding sections |
| `META-INF/ALIAS.RSA`, `.DSA`, or `.EC` | Signature block containing the digital signature and signer certificate information |

The signature file names depend on the alias and signature algorithm. For example, a signer alias `release-signer` may produce files such as `RELEASE-S.SF` and `RELEASE-S.RSA`; exact names may be truncated according to JAR signing rules.

The signature block uses the PKCS#7/CMS format to carry the signature and associated certificates. The certificate chain of the private-key entry in the keystore is used during signing and may be embedded in the signature block so the recipient can build the chain.

Typically, the root CA does not need to be shipped with the JAR. The recipient should have the root CA in their own truststore or managed CA store. Required intermediate certificates can be included in the signature block to help construct the chain.

A JAR signature does not encrypt the contents. Recipients can still read classes and resources; the signature is used to detect tampering and verify the signing source.

## 3. Keystore, Certificate Chain, and Truststore

These three concepts are related but not interchangeable.

| Component | Contents | Who Uses It? |
|---|---|---|
| Signing keystore | Signer's private key and corresponding certificate chain | Person/build system signing the JAR |
| Certificate chain | Leaf certificate and intermediate CA certificates | Provided by the signer; used by the verifier to validate the path |
| Truststore | Root CA or trusted certificates | Person/machine verifying the JAR |

In Java `KeyStore`, an entry holding a private key is typically a `PrivateKeyEntry`. That entry contains the private key and its corresponding certificate chain. An entry containing only a trusted certificate is typically a `trustedCertEntry`.

Do not distribute the signing keystore to JAR recipients. Recipients only need the signed JAR and a truststore containing the trusted CA. The private key must be protected separately.

## 4. Preparing a Key Pair and Signing Keystore

With JDK 17, `PKCS12` is the default keystore format and is appropriate for new projects. The example below creates a test key pair using 3072-bit RSA.

~~~powershell
keytool -genkeypair -alias release-signer -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -storetype PKCS12 -keystore signing.p12 -validity 365 -dname "CN=Example Release, OU=Build, O=Example, C=VN"
~~~

`keytool` will prompt for the keystore password and private key password if needed. Do not pass real passwords via `-storepass` or `-keypass` on the command line, as they can appear in shell history, process listings, or logs.

Inspect the newly created entry:

~~~powershell
keytool -list -v -alias release-signer -keystore signing.p12 -storetype PKCS12
~~~

In a self-signed example, the entry is a `PrivateKeyEntry` and the certificate chain usually has only one certificate. This setup is suitable for learning and internal testing; a self-signed certificate is not trusted externally by default.

For production releases, use a code-signing certificate issued through a CA or organizational process. The certificate should have appropriate usage attributes, including key usage and extended key usage per CA policy. Verify the issuer, validity, subject, and algorithms before signing.

## 5. Generating a CSR for a CA-Issued Signer Certificate

In a release environment, the signer keeps the private key in the keystore and sends a CSR to the CA. The CSR contains the public key and subject information; the private key never leaves the signing keystore.

Generate a CSR from the correct alias:

~~~powershell
keytool -certreq -alias release-signer -keystore signing.p12 -storetype PKCS12 -file release-signer.csr
~~~

Inspect the CSR contents:

~~~powershell
keytool -printcertreq -file release-signer.csr
~~~

CA workflow:

1. Generate the key pair in the signing keystore.
2. Generate a CSR from the alias containing the private key.
3. Submit the CSR to the CA following your organization's identity verification process.
4. The CA returns the signer certificate and chain, typically in PEM or PKCS#7 format.
5. Verify the CA certificate and fingerprint through an independent channel.
6. Import the required CA certificates and the certificate reply into the keystore.
7. Re-check the chain on the private-key entry before signing any JAR.

A CA may apply its own policies for subject, key usage, extended key usage, and validity period. Do not assume every extension in the CSR is preserved by the CA; inspect the actual issued certificate.

## 6. Verifying CA Certificates Before Importing

Before adding a certificate as a trust anchor, inspect its contents and fingerprint:

~~~powershell
keytool -printcert -file root-ca.pem
~~~

Compare the SHA-256 fingerprint against a value obtained through an independent, trusted channel—such as an authenticated CA portal, signed internal PKI documentation, or a PKI administrator. Do not verify a certificate solely by comparing it against a fingerprint sent alongside the same file.

Check the following:

- Subject and issuer match the expected CA.
- SHA-256 fingerprint matches the independent source.
- The certificate is currently valid.
- Basic Constraints properly identify the CA certificate's role.
- Key Usage allows certificate signing.
- The chain includes any required intermediate CAs.

Do not import an unverified certificate of unknown origin into a truststore just to make a verification command succeed. When you trust a root CA, you allow certificates issued under that root's policy to be considered trustworthy.

## 7. Building the Chain in the Signing Keystore

If the CA returns the signer certificate and intermediate chain in a PKCS#7 file, you can import the certificate reply into the exact alias containing the private key.

When necessary, import the verified root/intermediate CAs as trusted certificates first. For example:

~~~powershell
keytool -importcert -alias organization-root -file root-ca.pem -keystore signing.p12 -storetype PKCS12
~~~

If there is an intermediate CA:

~~~powershell
keytool -importcert -alias organization-intermediate -file intermediate-ca.pem -keystore signing.p12 -storetype PKCS12
~~~

Once the trust anchor/chain is prepared, import the certificate reply into the alias that generated the CSR:

~~~powershell
keytool -importcert -alias release-signer -file signer-reply.p7b -keystore signing.p12 -storetype PKCS12 -trustcacerts
~~~

The `release-signer` alias must be the private-key entry that created the CSR. The public key in the certificate reply must match the public key of that private key. If you use a new alias, `keytool` may create a separate trusted certificate entry instead of updating the private key's chain.

Inspect the chain after importing:

~~~powershell
keytool -list -v -alias release-signer -keystore signing.p12 -storetype PKCS12
~~~

Check `Certificate chain length` and each certificate in the chain. In a CA chain, the signer certificate typically appears first, followed by intermediate CAs; the root trust anchor is resolved from the truststore. If the chain is incomplete or mismatched, stop before signing and request the proper chain from the CA.

## 8. Creating a Sample JAR to Sign

This example uses a small Java application to build an executable JAR.

Project structure:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── Main.java
├── classes/
└── app.jar
~~~

Contents of `src/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        String target = args.length == 0 ? "Java" : String.join(" ", args);
        System.out.println("Hello, " + target + "!");
    }
}
~~~

From the `project` root directory, compile and package:

~~~powershell
New-Item -ItemType Directory -Force -Path classes | Out-Null
javac -d classes src/com/example/Main.java
jar --create --file app.jar --main-class com.example.Main -C classes .
~~~

Run the unsigned JAR to test the program:

~~~powershell
java -jar app.jar "before signing"
~~~

Stdout:

~~~text
Hello, before signing!
~~~

Only sign after confirming the final artifact. Do not modify or update JAR contents after signing; modifying a signed entry invalidates its digest.

## 9. Signing the JAR with jarsigner

Use the signing keystore and the alias containing the private key:

~~~powershell
jarsigner -keystore signing.p12 -storetype PKCS12 -sigalg SHA256withRSA -digestalg SHA-256 -signedjar app-signed.jar app.jar release-signer
~~~

Arguments:

- `-keystore signing.p12`: signing keystore.
- `-storetype PKCS12`: keystore format.
- `-sigalg SHA256withRSA`: algorithm for signing the signature file.
- `-digestalg SHA-256`: digest algorithm for JAR contents.
- `-signedjar app-signed.jar`: writes the signed JAR to a new file, leaving `app.jar` untouched.
- `app.jar`: source JAR to sign.
- `release-signer`: private-key entry alias.

`jarsigner` prompts for the keystore/private key password if not provided on the command line. For releases, use modern algorithms permitted by the JDK and security policies; avoid MD5, SHA-1, and weak algorithms.

After signing, the JAR contains signature metadata under `META-INF`. List the files:

~~~powershell
jar --list --file app-signed.jar
~~~

You will see `META-INF/MANIFEST.MF` and signature files with extensions such as `.SF`, `.RSA`, `.DSA`, or `.EC`. The signature block contains the signature and signer certificate; the chain helps recipients build a trust path.

Run the signed JAR itself:

~~~powershell
java -jar app-signed.jar "signed artifact"
~~~

Stdout:

~~~text
Hello, signed artifact!
~~~

Successful execution shows that the launcher can run the application from the archive. It does not replace verifying the signature or trust chain.

## 10. Verifying the Signature and Certificate Chain

Verify the JAR signature:

~~~powershell
jarsigner -verify -verbose -certs app-signed.jar
~~~

Options:

- `-verify`: verifies digests and signatures of signed entries.
- `-verbose`: displays entries and verification status.
- `-certs`: displays certificate information for the signer/chain.

You can also use `keytool` to inspect the certificates embedded in the JAR:

~~~powershell
keytool -printcert -jarfile app-signed.jar
~~~

Check the signer certificate, issuer, fingerprint, validity, and chain. Exact output depends on the certificate, JDK version, and the machine's trust state.

### 10.1. Verifying with a Specific Truststore

To verify the chain against a CA trusted by your organization, supply a truststore containing the verified root CA:

~~~powershell
jarsigner -verify -strict -verbose -certs -keystore verify-truststore.p12 -storetype PKCS12 app-signed.jar
~~~

`verify-truststore.p12` is the verifier's truststore, not the signing keystore containing the private key. You can create a truststore by importing the verified root CA:

~~~powershell
keytool -importcert -alias organization-root -file root-ca.pem -keystore verify-truststore.p12 -storetype PKCS12
~~~

If your organization uses a public CA, configure a truststore appropriate for the verification environment. Do not assume one machine's truststore has the same CA roots as another.

### 10.2. What -strict Means

`-strict` tells `jarsigner` to treat severe warnings during verification as errors and return a non-zero exit code when those conditions occur. This is the recommended option for release/CI verification steps.

Do not check only the summary line. Review diagnostics, the certificate chain, timestamps, and per-entry status. A JAR may have a cryptographically valid signature while the signer certificate is not yet trusted by the truststore.

## 11. Distinguishing Integrity, Signature, and Trust

| Check | Question | Evidence |
|---|---|---|
| Digest/integrity | Has any entry been modified since signing? | Entry digest matches manifest/signature file |
| Digital signature | Was the signature file signed by the corresponding private key? | Signature verifies using the public key in the signer certificate |
| Certificate chain | Does the signer certificate have a valid path to a CA? | Valid chain, CA signatures, validity periods, and constraints |
| Trust | Is the root CA accepted by the recipient? | Trust anchor is present in the configured truststore |
| Timestamp | At what time did the signature already exist? | Valid timestamp token from a trusted TSA |

A structurally valid certificate chain is not enough to establish trust if the root CA is not in the truststore. Conversely, adding a certificate to a truststore is a trust decision by the verifier; it does not fix a tampered JAR signature.

Nor does a JAR signature prove that the code is safe or free of vulnerabilities. It verifies that the contents match the signed artifact and confirms the signer's identity according to the trust policy.

## 12. Timestamping JAR Signatures

A signer certificate has an expiration date. If a JAR is signed while the certificate is valid but verified after the certificate expires, the verifier may need proof of when the signing occurred.

`jarsigner` supports obtaining a timestamp from a Time-Stamp Authority (TSA) via `-tsa`:

~~~powershell
jarsigner -keystore signing.p12 -storetype PKCS12 -sigalg SHA256withRSA -digestalg SHA-256 -tsa https://tsa.example.org -signedjar app-timestamped.jar app.jar release-signer
~~~

Replace the example URL with an actual TSA endpoint designated by your CA or trusted provider. The TSA creates a timestamp token bound to the signature; the token has its own certificate chain that must be verified.

A timestamp helps prove that the signature existed at a time attested by the TSA. It does not make an invalid signature valid, does not recover a compromised private key, and does not replace checking the signer's or TSA's certificate chain.

For long-lived release artifacts, timestamping is usually an essential part of the code-signing workflow. Check the timestamp in `jarsigner -verify -verbose -certs` output and ensure the TSA is accepted by the verification environment's truststore.

## 13. Unsigned Entries and Modifying a JAR After Signing

A JAR can contain unsigned entries—for example, files added after signing or content not covered by the signature. Therefore:

- Use `-verbose` to inspect the status of every entry.
- Confirm that all critical classes and resources are signed.
- Do not rely solely on the `jar verified` line and ignore warnings about unsigned entries.
- Sign after the final packaging step.
- If a signed entry changes, rebuild the JAR and re-sign the entire artifact.

If a signed entry is modified, its digest no longer matches and verification must detect the change. If an entry is unsigned, the signature provides no integrity guarantee for that entry.

Do not update the manifest or add resources to a JAR after signing. Finish building the archive, verify its contents, then sign and verify the exact file you will release.

## 14. Common Certificate Chain Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| `certificate chain not validated` | Chain cannot be built or trust anchor is missing | Provide verified intermediate and root CAs in the truststore |
| `signer certificate is self-signed` | Self-signed certificate is not trusted by the verifier | Trust only in test environments; use a CA code-signing certificate for releases |
| `unable to find valid certification path` | Root/intermediate missing from truststore or broken chain | Check issuer/subject, import the proper CA chain, and verify the root |
| `Certificate reply does not contain public key for ...` | CA reply does not match the private key that generated the CSR | Use the correct alias/CSR or ask the CA to reissue the certificate |
| `Certificate expired` | Leaf or intermediate certificate has expired | Renew/reissue the certificate and check timestamping if present |
| Inappropriate host/usage | Certificate was issued for a different purpose | Use a certificate with key usage/EKU suitable for code signing |
| `digest error` or `signature invalid` | JAR entry was modified or file corrupted after signing | Rebuild the artifact from trusted sources and re-sign |
| `jar verified` with unsigned entries | Some entries are outside the signature's scope | Inspect verbose output and re-sign the complete JAR |
| Invalid timestamp | Invalid TSA chain, timestamp token, or digest | Check TSA URL, TSA certificate, clock, and algorithms |
| `-strict` returns non-zero exit code | Severe warning about trust, chain, expiration, or algorithms | Read all diagnostics and resolve the root cause before releasing |

Do not resolve trust errors by importing an arbitrary signer certificate into the truststore without verification. The truststore determines which CAs are accepted; importing the wrong certificate can undermine the entire verification policy.

## 15. Release Workflow for JARs with a Certificate Chain

A secure release workflow may include:

1. Build the complete JAR from reviewed source code.
2. Create or access the signing key in a protected keystore or signing device.
3. Inspect the signer certificate and chain.
4. Verify the root CA fingerprint through an independent channel.
5. Import the CA reply into the correct private-key alias.
6. Sign the JAR with `jarsigner` using approved digest and signature algorithms.
7. Obtain a timestamp from a trusted TSA when long-term releases require it.
8. Verify the JAR with `jarsigner -verify -verbose -certs`.
9. Verify the trust chain against a managed truststore and use `-strict` in CI.
10. Confirm every critical entry is signed and no content was added after signing.
11. Smoke-test the signed JAR and record the fingerprint, signer identity, build ID, and verification results.
12. Distribute the JAR; never distribute the signing keystore or private key.

For critical release systems, consider an HSM or signing service so the private key does not reside as an ordinary file on a build agent. Restrict key access, audit signing operations, and maintain a certificate rotation plan.

## 16. Pre-Release Checklist

- [ ] JAR is finalized before signing.
- [ ] Signing alias is a `PrivateKeyEntry` holding the correct private key.
- [ ] Signer certificate is appropriate for code signing.
- [ ] Certificate chain includes the signer and required intermediate certificates.
- [ ] Root CA fingerprint has been verified through an independent channel.
- [ ] Verifier's truststore contains the right trust anchor.
- [ ] Strong, JDK-approved digest and signature algorithms are used.
- [ ] Signed with `jarsigner` while keeping the original source JAR.
- [ ] `jarsigner -verify -verbose -certs` verifies the signature.
- [ ] `-strict` reports no severe warnings in CI.
- [ ] Unsigned entries and all critical entries have been checked.
- [ ] Valid timestamp is present if required by the release process.
- [ ] JAR is not modified after signing.
- [ ] Private key and signing keystore are protected and not distributed with the JAR.
- [ ] Verification results and signer details are recorded for auditing.

A certificate chain for JAR signing connects the signer's certificate to a root CA trusted by the recipient. `jarsigner` uses the private key to sign, embeds the signature and certificates into the JAR, and verifies digests and signatures during inspection. To verify the release source, the recipient also needs to build a chain to a trusted anchor, validate the certificates, and check the timestamp. Verify integrity, chain, trust, and per-entry status before every release.

## References

- Oracle, The jarsigner Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Oracle, The keytool Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- Oracle, JAR File Specification, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
