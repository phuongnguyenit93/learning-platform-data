# The jarsigner Command in Java

**`jarsigner`** is a JDK tool used to digitally sign JAR files and verify their digital signatures. When signing, the tool uses a private key in a keystore to generate signatures for the archive contents and writes signature metadata into the `META-INF` directory. When verifying, the tool checks the digests of the entries, the signature, and the signer's certificate.

JAR signing helps detect whether content has been modified after signing and binds the signature to the identity represented in the certificate. Signing does not encrypt the JAR contents, does not automatically make the certificate trusted, and does not replace application security checks.

## 1. What is JAR signing used for?

When distributing a Java library or application, recipients need to know whether the artifact is still intact and signed by the expected identity.

JAR signing supports:

- **Integrity:** detects whether signed content has been modified after the time of signing.
- **Signer identity:** identifies the certificate and public key associated with the signature.
- **Tamper detection:** detects entries whose digests no longer match.
- **Release verification:** verifies artifacts before deployment or distribution.
- **Multiple signers:** allows multiple parties to sign the same JAR according to a release workflow.

A signed JAR can still contain malware or bugs. A signature indicates that the content matches the signature of the corresponding private key; trusting the signer also depends on the certificate chain, trust policies, and key issuance processes.

## 2. Signature mechanism in a JAR

When signing a JAR, `jarsigner` updates or creates metadata files in `META-INF`. The main components are:

| Component | Role |
| --- | --- |
| `META-INF/MANIFEST.MF` | Contains digests of the entries in the JAR |
| `META-INF/<SIGNER>.SF` | Contains digests of the manifest or manifest sections |
| `META-INF/<SIGNER>.RSA`, `.DSA`, or `.EC` | Signature block containing the digital signature and corresponding certificate information |

The signature file name is generated from the signer name or the `-sigfile` option; the signature block file extension depends on the key algorithm.

Conceptual workflow:

1. Jarsigner computes a digest for the content of each entry to be signed.
2. The digests are recorded in the manifest.
3. The tool creates a `.SF` signature file containing digests of the manifest or its sections.
4. The private key signs the signature file.
5. The signature and certificate chain are stored in the signature block.
6. When verifying, the tool recomputes the digests and verifies the signature using the public key in the certificate.

If the content of a signed entry is modified, the digest will not match and verification will report an error. If a new entry is added after signing, that entry is not automatically protected by the old signature; verifiers may see an unsigned entry. Therefore, always sign after all changes to the JAR are complete.

## 3. Preparing a keystore and key pair

Jarsigner requires a private key to sign. The key is usually stored in a keystore along with its certificate.

For modern JDKs, PKCS12 is the appropriate choice for a new keystore. Example of generating an RSA key pair for testing:

```bash
keytool -genkeypair -alias release-key -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 365 -storetype PKCS12 -keystore release-signing.p12 -dname "CN=Example Test Signer, OU=Engineering, O=Example Org, C=VN"
```

Meaning of the options:

- `-genkeypair`: generates a private key and public key.
- `-alias release-key`: entry name in the keystore.
- `-keyalg RSA`: uses the RSA algorithm.
- `-keysize 3072`: 3072-bit RSA key size.
- `-sigalg SHA256withRSA`: certificate signature algorithm.
- `-validity 365`: validity period of the self-signed certificate is 365 days.
- `-storetype PKCS12`: keystore format.
- `-keystore release-signing.p12`: output keystore file.
- `-dname`: Distinguished Name of the subject in the certificate.

Keytool will prompt you to enter and confirm a password. Enter it interactively instead of putting passwords directly on the command line, in scripts, or in shell history. With PKCS12, the password protecting the private key usually uses the same password as the keystore.

The self-signed certificate in this example is suitable for learning and testing. For real releases, use a code-signing certificate that aligns with your organization's workflow or a CA trusted by recipients. Do not use test certificates as production release identities.

Inspect the entry:

```bash
keytool -list -v -alias release-key -keystore release-signing.p12 -storetype PKCS12
```

Confirm that the entry type is `PrivateKeyEntry`, the key algorithm is correct, and the certificate is the one associated with the expected alias.

## 4. Basic syntax of jarsigner

Signing syntax:

```text
jarsigner [options] jar-file alias
```

Verification syntax:

```text
jarsigner -verify [options] jar-file [alias...]
```

Parameters:

- `jar-file`: the JAR to sign or verify.
- `alias`: alias of the entry containing the private key and certificate in the keystore.
- `options`: keystore, digest/signature algorithms, timestamp, and output options.

View help on the JDK currently in use:

```bash
jarsigner -help
jarsigner -version
```

Commonly used options:

| Option | Purpose |
| --- | --- |
| `-keystore <url>` | Keystore location |
| `-storetype <type>` | Keystore type, e.g., PKCS12 |
| `-storepass <password>` | Keystore password |
| `-keypass <password>` | Private key password if different |
| `-signedjar <file>` | Output JAR file name after signing |
| `-digestalg <algorithm>` | Digest algorithm |
| `-sigalg <algorithm>` | Signature algorithm |
| `-tsa <url>` | Timestamping Authority URL |
| `-tsacert <alias>` | TSA certificate alias in the keystore |
| `-tsadigestalg <algorithm>` | Digest algorithm for the timestamp request |
| `-verify` | Verify a signed JAR |
| `-verbose` | Display detailed information |
| `-certs` | Display certificates when verifying in verbose mode |
| `-strict` | Treat warnings as errors |
| `-sigfile <file>` | Base name for signature files |

Some options depend on the JDK version or provider. Use `jarsigner -help` in your build/release environment to confirm.

## 5. Signing a JAR with a private key

Suppose you already have a JAR `app.jar` and a keystore `release-signing.p12` containing the alias `release-key`.

Sign and write the result to a new file:

```bash
jarsigner -keystore release-signing.p12 -storetype PKCS12 -digestalg SHA-256 -sigalg SHA256withRSA -signedjar app-signed.jar app.jar release-key
```

Explanation:

- `-keystore release-signing.p12`: keystore containing the private key.
- `-storetype PKCS12`: keystore format.
- `-digestalg SHA-256`: uses SHA-256 to compute content digests.
- `-sigalg SHA256withRSA`: uses RSA with SHA-256 to sign the signature file.
- `-signedjar app-signed.jar`: writes the signed JAR to a new file.
- `app.jar`: source JAR.
- `release-key`: alias of the private key used for signing.

Jarsigner will prompt for the keystore password and, if necessary, the private key password. Do not pass real passwords in commands or configuration files that could be captured in logs.

Using `-signedjar` preserves the source JAR for comparison or re-signing. If you omit this option, jarsigner can update the input JAR in place; in release workflows, use a separate output artifact for easier control.

## 6. Inspecting a signed JAR

List archive contents:

```bash
jar --list --file app-signed.jar
```

In a signed JAR, there will typically be signature files in `META-INF`, alongside the manifest and the original classes/resources.

Verify the signature:

```bash
jarsigner -verify -verbose -certs app-signed.jar
```

Options:

- `-verify`: requests signature verification.
- `-verbose`: displays entry statuses and verification details.
- `-certs`: displays the certificate chain associated with the signature.

You can also use summary mode:

```bash
jarsigner -verify -verbose:summary -certs app-signed.jar
```

The output may indicate that the JAR is cryptographically verified while also displaying warnings if the certificate is self-signed, the certificate chain is untrusted, or there are validity/policy issues.

Do not just look at the `jar verified` line. Read all warnings and check every entry that should be signed. A JAR can contain unsigned entries or an untrusted certificate even if signature verification succeeds for some entries.

## 7. Distinguishing integrity from certificate trust

This is the most important distinction when reading verification output.

**Integrity/signature verification** answers: does the signed content still match the digest and signature?

**Certificate trust** answers: should the signer's identity be trusted based on the certificate chain, CA, validity period, policies, and revocation status?

For example, a JAR signed with a self-signed certificate can pass the mathematical signature check while still producing a warning that the certificate is not trusted. The recipient needs to verify the certificate fingerprint through an independent channel and decide whether to trust the signer.

Factors affecting trust:

- Was the certificate issued by a trusted CA or trust anchor?
- Is the certificate valid at the appropriate signing/verification time?
- Does the certificate have the appropriate key usage for code signing?
- Is the certificate chain complete and valid?
- Is there reliable timestamp information?
- Does the policy require revocation checking?
- Are the algorithm and key length disabled by the JDK security policy?

Do not import a certificate into a truststore just to silence warnings without first verifying its origin and fingerprint.

## 8. Using -strict in verification workflows

The `-strict` option tells jarsigner to treat warnings as errors:

```bash
jarsigner -verify -strict -verbose -certs app-signed.jar
```

This is useful in CI or release pipelines where every signature/certificate warning must be addressed.

With the self-signed certificate in the learning example, strict mode may return a failure status because the certificate is untrusted. This is expected in a test environment and does not necessarily mean the mathematical signature is broken.

In a release pipeline, configure the truststore and certificate chain properly before enabling strict mode. Do not relax checks just to make the pipeline green without understanding the warnings.

Distinction:

- `-verify` enables signature checking.
- `-strict` turns warnings into errors.
- `-certs` displays certificates to help evaluate the signer.
- `-verbose` provides details about entries and results.

## 9. Timestamping signatures with a TSA

When signing a JAR for long-term distribution, you can add a timestamp from a **Timestamping Authority (TSA)**.

Example syntax:

```bash
jarsigner -keystore release-signing.p12 -storetype PKCS12 -digestalg SHA-256 -sigalg SHA256withRSA -tsa <TSA_URL> -signedjar app-timestamped.jar app.jar release-key
```

Replace `<TSA_URL>` with the actual TSA URL designated by your organization or a trusted provider.

A timestamp is TSA-signed proof recording that the signature existed at a specific point in time. It is useful when the code-signing certificate expires after the signing date: if the timestamp and certificate chain are valid, the verifier can determine that the signature was created while the certificate was still valid.

Key points to remember:

- The TSA must be trusted by the verifying party.
- The build machine needs network access to the TSA during signing.
- A timestamp does not turn a self-signed certificate into a trusted certificate.
- A timestamp cannot fix an invalid signature or modified content.
- A timestamp does not eliminate all certificate revocation or weak algorithm issues.
- If the TSA is unreachable or returns an invalid timestamp, signing may fail or fail to include the desired timestamp.

You can specify the digest algorithm for the timestamp using `-tsadigestalg SHA-256` when explicit configuration is needed and supported by the JDK/provider.

## 10. Signing a JAR with a CA-issued certificate

In a release environment, the workflow usually does not stop at a self-signed certificate.

General workflow:

1. Generate a key pair in the keystore.
2. Create a CSR using `keytool -certreq`.
3. Submit the CSR to a CA or certificate issuance service following your code-signing process.
4. The CA verifies the organization/requester and issues the certificate along with its chain.
5. Import the certificate reply into the exact alias containing the private key.
6. Verify the certificate chain using `keytool -list -v`.
7. Use jarsigner to sign the JAR with that alias.
8. Add a timestamp from an appropriate TSA.
9. Verify the JAR in an environment with the corresponding truststore.

Generate a CSR:

```bash
keytool -certreq -alias release-key -keystore release-signing.p12 -storetype PKCS12 -file release-signing.csr
```

Import the certificate reply:

```bash
keytool -importcert -alias release-key -file signing-certificate-chain.pem -keystore release-signing.p12 -storetype PKCS12
```

The certificate reply file must match the public key in the CSR and have a valid chain according to the CA's requirements. Do not generate a new key pair between submitting the CSR and importing the certificate reply; if the key changes, the old CSR will no longer match.

## 11. Signing a JAR with multiple signers

A JAR can contain signatures from multiple signers. For example, an organization may require both the build team and a release authority to sign the artifact according to separate processes.

In principle:

- Each signer uses its own private key.
- Each signer creates its own signature metadata in `META-INF`.
- Signatures can be verified independently.
- Adding a signer does not replace or vouch for a previous signer.
- All signers must sign the same artifact contents according to an agreed-upon workflow.

Conceptual example: sign the JAR with the first signer, then sign the signed JAR with the second signer using a different keystore/alias. Verify all signatures after the final step:

```bash
jarsigner -verify -verbose -certs app-multisigned.jar
```

In practice, you must manage the signing order, timestamps, certificate chains, and trust policies of each signer. Do not modify the JAR contents after the parties have signed it.

## 12. What invalidates a JAR signature?

Signatures rely on content digests. The following operations can cause verification to fail or leave entries unprotected:

- Modifying bytecode or resources of a signed entry.
- Replacing a class file in the archive.
- Modifying the manifest or signature metadata in a way that causes digests/signatures to no longer match.
- Deleting or modifying signature files.
- Adding new entries after signing without re-signing: the new entries are not protected by the old signature.

Example of a broken workflow:

1. Build the JAR.
2. Sign the JAR.
3. Update a configuration file inside the JAR.
4. Distribute the JAR without re-signing.

Correct workflow:

1. Finish building all classes, resources, and configurations.
2. Inspect the JAR contents.
3. Sign the final artifact.
4. Verify the signature.
5. Record checksums and release the exact verified artifact.

If you need to modify a JAR after signing, build a new artifact and re-sign the entire final content.

## 13. Digest and signature algorithms

These two options serve different roles:

- `-digestalg`: algorithm for hashing entry contents.
- `-sigalg`: algorithm used with the private key to sign the signature file.

Example with RSA:

```bash
jarsigner -digestalg SHA-256 -sigalg SHA256withRSA ...
```

Example with EC:

```bash
jarsigner -digestalg SHA-256 -sigalg SHA256withECDSA ...
```

Choosing algorithms requires considering:

- Current security policies.
- Compatibility with the JDK and target platforms.
- The type of private key in the keystore.
- Organizational or CA requirements.
- JDK security properties, which may reject weak or disabled algorithms.

Avoid using MD5 or SHA-1 for new release signatures. Do not choose an outdated algorithm solely for compatibility with an older runtime without explicitly evaluating the risks and support policies.

## 14. Inspecting signature metadata contents

After signing, you can list the JAR contents:

```bash
jar --list --file app-signed.jar
```

Look for entries in `META-INF`, for example:

```text
META-INF/MANIFEST.MF
META-INF/RELEASE.SF
META-INF/RELEASE.RSA
com/example/Main.class
config/application.properties
```

The name `RELEASE` is just an example; jarsigner derives signature file names from the signer or the `-sigfile` setting.

You can view the signed manifest:

```bash
unzip -p app-signed.jar META-INF/MANIFEST.MF
```

The `unzip` command is an OS utility, not a JDK command. If it is not available, use `jar --extract` to extract the manifest into a temporary directory and read the file.

Do not edit `.SF`, `.RSA`, `.DSA`, or `.EC` files directly. They are part of the signature structure; modifying them will invalidate verification.

## 15. Automation in CI/CD

A secure JAR signing pipeline typically includes:

1. Build the JAR from reviewed source code.
2. Run unit tests and dependency checks.
3. Retrieve the signing key from a controlled key vault or signing service.
4. Sign the artifact with approved digest and signature algorithms.
5. Request a TSA timestamp if required by the release policy.
6. Verify the signature using `jarsigner -verify`.
7. Run `-strict` once the truststore and certificate chain are properly configured.
8. Check for unsigned entries and warnings.
9. Store the artifact, checksums, signer identity, and verification results.
10. Release the exact artifact that was signed and verified.

Protecting the pipeline:

- Do not store private keys in the repository.
- Do not print keystore passwords to logs.
- Prefer a secret manager, HSM, or centralized signing service where appropriate.
- Restrict access to the signing key to build accounts.
- Separate test and production keys.
- Monitor expiration dates and certificate rotation processes.
- Retain signing and timestamp evidence as required for auditing.

If using secret injection, ensure secrets do not appear in process logs, build scans, command history, or artifacts.

## 16. Common errors when signing and verifying JARs

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Cannot open keystore | Wrong path, password, or store type | Check `-keystore`, `-storetype`, and password |
| Alias not found | Alias does not exist or is misspelled | Use `keytool -list` to check |
| No private key to sign | Entry is a `trustedCertEntry`, not a `PrivateKeyEntry` | Use an alias that has a private key |
| Signature algorithm error | Algorithm is incompatible with the key or blocked by security policy | Choose a supported and approved algorithm |
| JAR reports digest error | Entry was modified after signing or archive is corrupted | Rebuild the final JAR and re-sign |
| JAR verified but has trust warning | Self-signed certificate or untrusted chain | Verify signer/fingerprint and configure trust appropriately |
| Strict verification fails | Warnings were elevated to errors by `-strict` | Read warnings, resolve trust/timestamp/entry issues, and re-run |
| TSA not responding | Wrong TSA URL, blocked network, or service error | Check endpoint, proxy, and timestamp service |
| Expired certificate | Certificate is no longer valid under verification policy | Use a valid timestamp if available and follow certificate issuance/rotation |
| Unsigned entries present | Files were added after signing or JAR was only partially signed | Finalize the archive and re-sign |
| JAR runs but signer is untrusted | Integrity does not equal certificate trust | Check chain, CA, and runtime trust policy |

## 17. Recommended JAR signing workflow

A repeatable release workflow:

1. Build the complete artifact and identify the exact output JAR.
2. Inspect the manifest and entry list.
3. Confirm the keystore has the right `PrivateKeyEntry` alias.
4. Choose SHA-256 or stronger for the digest and a signature algorithm compatible with the key.
5. Sign to a new file using `-signedjar`.
6. Add a TSA timestamp if required by the release policy.
7. Verify with `jarsigner -verify -verbose -certs`.
8. Check warnings and certificate trust; use `-strict` in CI once proper trust is established.
9. Verify that the JAR contains no unexpected or unsigned entries.
10. Store the artifact and verification evidence.
11. Distribute the certificate/public key via a trusted channel so recipients can verify the signer.

Do not modify the artifact after completing the signing step. If content changes, rebuild and re-sign.

## 18. Key takeaways

- `jarsigner` uses a private key in a keystore to sign a JAR and uses the public key/certificate to verify it.
- `jarsigner -keystore ... -signedjar ... jar alias` signs the JAR into a new file.
- `-digestalg` selects the digest algorithm; `-sigalg` selects the signature algorithm.
- `jarsigner -verify -verbose -certs` checks signatures and displays certificates.
- `-strict` turns warnings into errors, making it suitable for release pipelines with a clear trust configuration.
- `-tsa` requests a timestamp from a TSA.
- Signature integrity is different from certificate trust.
- Self-signed certificates can be used for testing but are not automatically trusted in production.
- Modifying a JAR after signing breaks the integrity of signed entries; newly added entries are not protected by the old signature.
- Private keys and keystore passwords must be protected and never committed or written to logs.

Once you master the workflow of generating a key pair → signing a JAR → timestamping → verifying signatures and certificates, you can release Java artifacts whose integrity and signing source can be verified in a controlled manner.
