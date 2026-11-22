# Signature algorithms in jarsigner

## 1. What is a signature algorithm?

A signature algorithm (digital signature algorithm) is an algorithm that uses a private key to generate a signature and the corresponding public key to verify it. In Java, the `jarsigner` tool uses digital signatures to verify the integrity of JAR entries and identify the signer's certificate.

A JAR signature provides two primary properties:

- **Integrity:** the signed entry content has not been modified since signing. If the data changes, the digest or signature check will fail.
- **Authenticity:** the signature was created using the private key corresponding to the public key in the signer's certificate. Recipients can use the certificate and trust chain to evaluate the signer's identity.

A digital signature does not encrypt the JAR contents. Recipients can still read classes, resources, and other files inside the archive. Nor does it prove on its own that the software is safe; it indicates whether the contents match the signature and signing key.

`jarsigner` uses a private key retrieved from a keystore to sign, then embeds the signature and corresponding certificate into the JAR. During verification, the tool uses the public key in the certificate to validate the signature.

## 2. Distinguishing digest algorithms and signature algorithms

When signing a JAR, two types of algorithms are typically configured separately:

| Component | Option | Role |
|---|---|---|
| Message digest | `-digestalg` | Computes a hash of each JAR entry's content and writes the digest to the manifest. |
| Digital signature | `-sigalg` | Signs the `.SF` signature file using the signer's private key. |

A digest is a fixed-length hash value computed from data. It does not use a private key and does not authenticate the signer's identity on its own.

A signature algorithm combines an asymmetric signing mechanism with a corresponding digest or signature parameters. During verification, the tool checks the signature using the public key.

Example:

~~~bash
jarsigner -digestalg SHA-256 -sigalg SHA256withRSA ...
~~~

In this command:

- `SHA-256` is the digest algorithm for the entries in the JAR.
- `SHA256withRSA` is the algorithm for signing the `.SF` file with an RSA key.
- The `SHA-256` part in the name `SHA256withRSA` is the digest used internally by the RSA signature algorithm.

The two options are related but are not the same configuration. You can use `-digestalg SHA-256` with `-sigalg SHA384withRSA` if the provider, security policy, and target environment support that combination.

## 3. Signature structure in a JAR

When signing a JAR, `jarsigner` updates the manifest and creates signature files in `META-INF`. For a single signer, the key components are:

~~~text
app-signed.jar
└── META-INF/
    ├── MANIFEST.MF
    ├── RELEASE.SF
    └── RELEASE.RSA
~~~

The specific filenames are derived from the alias or the `-sigfile` option. The signature block extension depends on the signing key type, such as `.RSA`, `.EC`, or `.DSA`.

The signing flow follows these steps:

1. Compute the digest of each entry's data and write the values to `META-INF/MANIFEST.MF`.
2. Create a `.SF` file containing digests of the manifest or its corresponding sections.
3. Sign the `.SF` file content using the private key.
4. Write the digital signature along with the certificate or certificate chain to the signature block.
5. Place these files into the `META-INF` directory of the JAR.

Role of each file:

- **MANIFEST.MF:** contains metadata and the digest of each signed entry.
- **.SF:** contains digests of the manifest and related sections; this is the data that is digitally signed.
- **.RSA / .EC / .DSA:** contains the signature of the `.SF` file along with the certificate needed for public-key verification.

The `.SF` file and signature block do not replace the manifest. They bind the entry digests to the signer's digital signature.

## 4. How JAR signatures are verified

When running `jarsigner -verify`, the tool checks the signature data chain in order:

1. Verify the digital signature of the `.SF` file using the public key in the certificate.
2. Check the digest of the manifest or each section in `.SF`.
3. Recompute the digest from the actual data of each entry and compare it with the value in the manifest.
4. Check for the use of algorithms disabled by the JDK's security properties.
5. Evaluate the certificate and certificate chain; warnings are displayed for the operator to review.

If the content of a signed entry is modified, the new digest will not match the manifest and verification will fail.

Two questions must be distinguished:

- **Is the signature cryptographically valid and is the content intact?**
- **Is the signer's certificate trusted in the receiving environment?**

A JAR may display `jar verified.` while still accompanied by warnings about a self-signed certificate or an untrusted certificate chain. A valid signature does not automatically make the signer's identity trusted.

## 5. Common signature algorithms

`jarsigner` supports multiple algorithms depending on the JDK version, provider, private key type, and security policy.

| Algorithm | Key type | Characteristics |
|---|---|---|
| `SHA256withRSA` | RSA | Combines SHA-256 with RSA PKCS#1 v1.5 signing; broadly compatible across modern JDKs. |
| `SHA384withRSA` | RSA | Uses SHA-384 with RSA; often selected as the default in some modern JDK configurations. |
| `SHA256withECDSA` | EC | Uses SHA-256 with the Elliptic Curve Digital Signature Algorithm. |
| `SHA384withECDSA` | EC | Uses SHA-384 with ECDSA. |
| `RSASSA-PSS` | RSA / RSASSA-PSS | RSA Probabilistic Signature Scheme; uses hash, salt, and mask generation function parameters. |
| `Ed25519` / `Ed448` | EdDSA | Edwards-curve signatures; the algorithm name is tied to the key's parameter set. |

Key points to remember:

- RSA, EC, RSASSA-PSS, and EdDSA select parameters differently.
- The signing algorithm must be compatible with the private key selected in the keystore.
- With RSASSA-PSS, the hash, MGF, and salt length parameters are part of the signature configuration.
- With Ed25519, the signature algorithm name is `Ed25519`; `-digestalg` still controls the JAR entry digest.
- DSA and algorithms based on SHA-1 or MD5 are legacy choices; do not use them to sign new artifacts unless there is an evaluated and approved compatibility requirement.

Standard algorithm names are case-insensitive. Consult the Java Security Standard Algorithm Names documentation to choose the exact name and verify provider support.

## 6. Algorithm defaults depend on JDK and key type

If `-sigalg` is not specified, `jarsigner` chooses a default signature algorithm compatible with the private key type and size. If `-digestalg` is not specified, the default also depends on the JDK version.

Do not assume a default will remain unchanged across all JDK releases. Oracle may update defaults and security policies to strengthen security.

In the verified JDK 24.0.2 environment:

- A JAR signed with a 3072-bit RSA key using default settings showed digest `SHA-384` and signature algorithm `SHA384withRSA`.
- When specifying `-digestalg SHA-256 -sigalg SHA256withRSA`, verification output showed `SHA-256` and `SHA256withRSA`.
- An EC P-256 key signed successfully with `SHA256withECDSA`.
- Ed25519 and RSASSA-PSS keys also signed and verified successfully.

These results reflect JDK 24.0.2 and its installed providers. When building for multiple runtimes, verify supported algorithms across all target versions instead of copying defaults from a development machine.

You can check the tool version:

~~~bash
jarsigner -version
java --version
~~~

Consult the standard algorithm list in the JCA/JCE documentation for the exact Java version you are using.

## 7. Preparing the keystore and signing key

`jarsigner` requires a keystore with an entry containing a private key and a certificate chain. The alias passed at the end of the command must point to a `PrivateKeyEntry`, not merely a trusted certificate entry.

Create a PKCS12 keystore for this example:

~~~bash
keytool -genkeypair \
  -alias releaseSigner \
  -keyalg RSA \
  -keysize 3072 \
  -dname "CN=Example Release Signer" \
  -validity 365 \
  -keystore release-signing.p12 \
  -storetype PKCS12
~~~

`keytool` will prompt for a keystore password and confirmation details. With PKCS12 by default, the password protecting the keystore is also used to protect the private key entry in this example.

Inspect the entry:

~~~bash
keytool -list -v \
  -keystore release-signing.p12 \
  -storetype PKCS12
~~~

Confirm the alias has:

~~~text
Entry type: PrivateKeyEntry
~~~

The keystore used in this example creates a self-signed certificate for testing. In a real release environment, use a certificate that complies with organizational policy, store the private key in an appropriate protected location, and distribute the certificate chain through a trusted process.

Do not commit keystores or private keys to a source repository, release JAR, or public artifact. Do not expose signing passwords in build logs.

## 8. Creating a sample JAR

Create a simple resource so digests can be observed:

~~~bash
mkdir -p input
printf "Original signed content\n" > input/message.txt
jar --create --file app.jar -C input .
jar --list --file app.jar
~~~

On Windows PowerShell, you can create the file and JAR as follows:

~~~powershell
New-Item -ItemType Directory -Force input | Out-Null
Set-Content -Encoding ascii input/message.txt "Original signed content"
jar --create --file app.jar -C input .
jar --list --file app.jar
~~~

The output includes the entries:

~~~text
META-INF/
META-INF/MANIFEST.MF
message.txt
~~~

Ensure all final classes and resources are included in the JAR before signing. If an entry's content is modified or replaced after signing, the signature for that entry will no longer be valid.

## 9. Signing a JAR with RSA and SHA-256

Use the keystore created in the previous section:

~~~bash
jarsigner \
  -keystore release-signing.p12 \
  -storetype PKCS12 \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  -signedjar app-signed.jar \
  app.jar \
  releaseSigner
~~~

If no password is passed on the command line, `jarsigner` will prompt for it when needed. This avoids placing passwords directly into command history.

After signing, inspect the structure:

~~~bash
jar --list --file app-signed.jar
~~~

In `META-INF`, files similar to the following will appear:

~~~text
META-INF/MANIFEST.MF
META-INF/RELEASE.SF
META-INF/RELEASE.RSA
~~~

Actual names depend on the alias and `-sigfile`. The `.RSA` extension indicates the signature block was created with an RSA key.

## 10. Inspecting digests and signatures in the archive

You can extract the manifest and signature file to inspect the digest fields:

~~~bash
jar --extract --file app-signed.jar META-INF/MANIFEST.MF
jar --extract --file app-signed.jar META-INF/RELEASE.SF
~~~

A section in the manifest may look like:

~~~text
Name: message.txt
SHA-256-Digest: <base64 digest>
~~~

The `.SF` file may contain:

~~~text
Signature-Version: 1.0
SHA-256-Digest-Manifest: <base64 digest>
SHA-256-Digest-Manifest-Main-Attributes: <base64 digest>

Name: message.txt
SHA-256-Digest: <base64 digest>
~~~

The Base64 values here only illustrate the structure. Actual values are generated from the JAR contents at signing time.

`MANIFEST.MF` contains digests of entry data. `.SF` contains digests of the manifest and corresponding sections. The signature block contains the signature of `.SF` and the certificate. This is why modifying file contents after signing causes verification to fail.

## 11. Verifying signatures and certificates

Basic verification:

~~~bash
jarsigner -verify app-signed.jar
~~~

To view entries, signer, and certificates:

~~~bash
jarsigner -verify -verbose:summary -certs app-signed.jar
~~~

The output may look like:

~~~text
- Signed by "CN=Example Release Signer"
    Digest algorithm: SHA-256
    Signature algorithm: SHA256withRSA, 3072-bit RSA key

jar verified.
~~~

If using a self-signed certificate, the output may include warnings about an untrusted certificate chain and a self-signed certificate. This does not mean the digest or cryptographic signature is invalid; it indicates the verifier does not yet have a suitable trust path.

When verifying in an environment with a truststore, pass the keystore containing the trusted certificate:

~~~bash
jarsigner -verify -strict \
  -keystore trusted-signers.p12 \
  -storetype PKCS12 \
  -verbose:summary \
  -certs \
  app-signed.jar
~~~

`-strict` causes severe warnings to be treated as errors. Read the full output, especially messages regarding the certificate chain, certificate status, timestamp, and algorithms.

`jar verified.` is the result of signature and integrity checking. It does not replace verifying the trust anchor, release policy, and signer identity in the deployment environment.

## 12. Testing when JAR content is modified

After signing, replace the content of a signed entry:

~~~bash
mkdir -p altered
printf "Modified content after signing\n" > altered/message.txt
jar --update --file app-signed.jar -C altered message.txt
jarsigner -verify app-signed.jar
~~~

The result will report a digest error or security exception similar to:

~~~text
jarsigner error: java.lang.SecurityException:
SHA-256 digest error for message.txt
~~~

This demonstrates that the signature is bound to the content at the time of signing. In a build pipeline, sign only after compilation, packaging, compression, and all JAR modification steps are complete.

If an artifact needs updating, rebuild the JAR from build sources and re-sign it. Do not directly modify resources or classes inside a released JAR.

## 13. Choosing an algorithm compatible with the private key

`-sigalg` must be compatible with the key type in the alias. Common combinations:

| Key created with keytool | Corresponding signature algorithm |
|---|---|
| `-keyalg RSA` | `SHA256withRSA`, `SHA384withRSA`, or `RSASSA-PSS` if supported by provider and policy. |
| `-keyalg EC` | `SHA256withECDSA` or `SHA384withECDSA`. |
| `-keyalg RSASSA-PSS` | `RSASSA-PSS` with appropriate parameters. |
| `-keyalg Ed25519` | `Ed25519`. |
| `-keyalg EdDSA` | EdDSA algorithm matching the key type and provider. |

Example creating an EC P-256 key:

~~~bash
keytool -genkeypair \
  -alias ecSigner \
  -keyalg EC \
  -groupname secp256r1 \
  -dname "CN=EC Release Signer" \
  -keystore ec-signing.p12 \
  -storetype PKCS12
~~~

Signing with ECDSA:

~~~bash
jarsigner \
  -keystore ec-signing.p12 \
  -digestalg SHA-256 \
  -sigalg SHA256withECDSA \
  -signedjar app-ec-signed.jar \
  app.jar \
  ecSigner
~~~

Example creating an Ed25519 key:

~~~bash
keytool -genkeypair \
  -alias edSigner \
  -keyalg Ed25519 \
  -dname "CN=Ed Release Signer" \
  -keystore ed-signing.p12 \
  -storetype PKCS12
~~~

Signing with Ed25519:

~~~bash
jarsigner \
  -keystore ed-signing.p12 \
  -signedjar app-ed-signed.jar \
  app.jar \
  edSigner
~~~

With Ed25519, the JDK may choose the entry digest independently, such as SHA-384, while the signature algorithm displays as `Ed25519`. Do not append `withRSA` or `withECDSA` to the algorithm name for an Ed25519 key.

If an incompatible algorithm is chosen, `jarsigner` will report an error such as:

~~~text
key algorithm not compatible with signature algorithm
~~~

Do not force an algorithm just to make the command run. Choose the key pair and signature algorithm as a matching pair.

## 14. RSASSA-PSS and signature parameters

`RSASSA-PSS` is a randomized RSA signature scheme. Unlike names like `SHA256withRSA`, PSS has parameters such as:

- Digest algorithm.
- Mask Generation Function, typically MGF1.
- MGF1 digest.
- Salt length.
- Trailer field.

If an RSASSA-PSS key was generated with encoded parameters, `jarsigner` uses those parameters. Otherwise, the tool selects parameters according to JDK rules and key size.

Example generating a key and signing:

~~~bash
keytool -genkeypair \
  -alias pssSigner \
  -keyalg RSASSA-PSS \
  -keysize 3072 \
  -dname "CN=PSS Release Signer" \
  -keystore pss-signing.p12 \
  -storetype PKCS12

jarsigner \
  -keystore pss-signing.p12 \
  -sigalg RSASSA-PSS \
  -signedjar app-pss-signed.jar \
  app.jar \
  pssSigner
~~~

PSS signed and verified successfully on JDK 24.0.2 in this guide's tests. Before using it in production, verify the provider, parameters, and all JDK runtimes that need to verify the artifact.

## 15. Timestamping signatures

A timestamp indicates that a signature existed at a point in time certified by a Time-Stamping Authority (TSA). It is useful when signing certificates have an expiration date: systems can verify that the JAR was signed while the certificate was still valid.

Use `-tsa` to specify the TSA URL:

~~~bash
jarsigner \
  -keystore release-signing.p12 \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  -tsa "$TSA_URL" \
  -signedjar app-timestamped.jar \
  app.jar \
  releaseSigner
~~~

Set the `TSA_URL` environment variable to an organization-approved TSA endpoint before running. When the TSA returns a timestamp token successfully, the token is stored with the signature block in the JAR.

Related options:

- `-tsa URL` specifies the TSA endpoint.
- `-tsacert alias` retrieves the TSA certificate from the keystore; the certificate must include Subject Information Access identifying the TSA URL.
- `-tsapolicyid OID` sends a policy identifier to the TSA.
- `-tsadigestalg algorithm` selects the digest used for the timestamp request's message imprint.

In JDK 24, the default digest for a timestamp request is SHA-384. This digest is independent of the `-digestalg` used for JAR entries.

A timestamp does not make an invalid signature valid, does not replace certificate chain verification, and does not prove content is safe. It provides evidence of when the signature was created.

## 16. Disabled algorithms and legacy algorithms

The JDK uses security properties to control algorithms considered insecure:

- `jdk.jar.disabledAlgorithms` lists algorithms not accepted when verifying JARs.
- `jdk.security.legacyAlgorithms` identifies older algorithms that may still be accepted with a warning.

If a signature uses a disabled algorithm, the JDK may treat the JAR as unsigned. If it uses a legacy algorithm, the tool may emit a warning that the algorithm will be disabled in a future update.

These properties reside in the `java.security` file in the JDK security configuration directory, typically `$JAVA_HOME/conf/security/java.security`.

Do not modify security properties on user machines just to make an old JAR verify. Re-sign with an accepted algorithm and test compatibility on target runtimes.

You can enable detailed diagnostics:

~~~bash
jarsigner -J-Djava.security.debug=jar -verify app-signed.jar
~~~

Review warnings and errors alongside the JDK version in use. Algorithm policies can change across JDK updates and organizational configurations.

## 17. Protecting passwords and private keys

Keystore and private key passwords should not appear in public scripts or CI logs.

`jarsigner` can prompt for passwords interactively. In automated environments, the tool supports reading passwords from environment variables or files using `-storepass:env`, `-storepass:file`, `-keypass:env`, and `-keypass:file`.

Example:

~~~bash
jarsigner \
  -keystore release-signing.p12 \
  -storepass:env JAR_STORE_PASSWORD \
  -keypass:env JAR_KEY_PASSWORD \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  app.jar \
  releaseSigner
~~~

Store these variables in your CI system's secret manager and grant access only to the signing job. Environment variables can still be exposed through configuration or process inspection; use an HSM, smart card, or PKCS#11 token when required by security policy.

With a configured PKCS#11 provider, `jarsigner` can access a token using `-keystore NONE -storetype PKCS11`. When using a hardware token, follow the device's PIN and protected authentication path procedures.

## 18. Signing a JAR with multiple signers

A JAR can be signed multiple times by different signers:

~~~bash
jarsigner app.jar releaseSignerA
jarsigner app.jar releaseSignerB
~~~

Each signer creates a separate signature file and signature block pair in `META-INF`. For example:

~~~text
META-INF/
├── RELEASEA.SF
├── RELEASEA.RSA
├── RELEASEB.SF
└── RELEASEB.RSA
~~~

This can be used when multiple organizations or publishers need to co-sign an artifact. Each signature can be verified independently; check which signers are required by your distribution policy.

If the content of a signed entry changes, the corresponding signatures will no longer verify. Perform all modifications before creating the final signatures.

## 19. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| `key algorithm not compatible with signature algorithm` | `-sigalg` is incompatible with the alias's private key. | Choose an algorithm matching the key type or generate a key pair of the right type. |
| `keystore was tampered with, or password was incorrect` | Incorrect password or keystore type. | Check `-storepass`, `-storetype`, and the keystore file. |
| `key associated with alias not a private key` | The alias points to a trusted certificate entry instead of a private key entry. | Use an alias with `Entry type: PrivateKeyEntry`. |
| `digest error for ...` | The entry was modified after signing or the file is corrupted. | Rebuild the JAR from original artifacts and re-sign. |
| `jar is unsigned` | The JAR lacks a valid signature block or uses a disabled algorithm. | Inspect `META-INF`, the algorithm, and the JDK security properties. |
| `jar verified` with a self-signed warning | The signature and digest are valid, but the certificate chain is not yet trusted. | Use an appropriate release certificate or a truststore with a managed trust anchor. |
| Warning that signature has no timestamp | The JAR has no timestamp token. | Use a TSA via `-tsa` or `-tsacert` according to release policy. |
| Algorithm works on one JDK but fails on another | Providers or security policies differ across versions. | Check standard algorithm names, providers, and `jdk.jar.disabledAlgorithms` on each runtime. |
| Provider not found for algorithm | The provider does not support the algorithm or is not configured. | Check the provider, JDK distribution, and `-addprovider`/`-providerClass` options if needed. |
| JAR has new entries that are unsigned | Entries were added after signing. | Finalize archive contents before signing and check for unsigned entries during verification. |

## 20. Signing and verification workflow in CI

A release pipeline might execute:

~~~bash
# 1. Create the final artifact
jar --create --file build/app.jar -C build/classes .

# 2. Sign with an approved key and algorithm
jarsigner \
  -keystore "$SIGNING_KEYSTORE" \
  -storepass:env JAR_STORE_PASSWORD \
  -keypass:env JAR_KEY_PASSWORD \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  -tsa "$TSA_URL" \
  -signedjar build/app-signed.jar \
  build/app.jar \
  releaseSigner

# 3. Verify the signature and certificate chain
jarsigner -verify -strict -verbose:summary \
  -keystore "$TRUSTSTORE" \
  -storetype PKCS12 \
  -certs \
  build/app-signed.jar
~~~

The pipeline should:

- Sign artifacts only after all build and JAR modification steps are complete.
- Store private keys in a secret manager or managed signing device.
- Use algorithms and key sizes approved by organizational policy.
- Configure a TSA if artifacts require proof of signing time.
- Verify using a JDK/runtime representative of the deployment environment.
- Review certificate chain, timestamp, and legacy algorithm warnings as part of release checks.
- Inspect output to ensure all expected entries are signed.
- Archive the signed artifact and verification report alongside the build revision.

Do not rely solely on exit codes or grepping for `jar verified`. Read the warnings and confirm the truststore, certificate chain, timestamp, and actual algorithms used.

## 21. Pre-release checklist

- The keystore alias points to a `PrivateKeyEntry`.
- The keystore and private key are protected and not committed to the repository.
- The key type is compatible with `-sigalg`.
- `-digestalg` is chosen according to security policy.
- The signature algorithm is supported by the provider and all target runtimes.
- JDK defaults are understood and unverified defaults are not relied upon.
- All files/resources are included in the JAR before signing.
- Manifest and signature files are present in `META-INF`.
- `jarsigner -verify` succeeds.
- The certificate chain and trust anchor have been verified.
- A timestamp is attached if required by the release process.
- No disabled algorithms or unresolved legacy warnings are present.
- It has been tested that modifying a signed entry causes verification to fail.
- The artifact and verification report are tied to the exact source/build revision.

## 22. References

- [The jarsigner Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- [JAR File Specification — Signed JAR File](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html)
- [Java Security Standard Algorithm Names — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/security/standard-names.html)
- [RFC 3161 — Internet X.509 Public Key Infrastructure Time-Stamp Protocol](https://www.rfc-editor.org/rfc/rfc3161)

`-digestalg` controls the digest of JAR entries, while `-sigalg` controls the algorithm used to sign the `.SF` file with the private key. Choose algorithms compatible with your key and target runtimes, understand the distinction between signature verification and certificate trust, and verify timestamps, security policies, and artifact integrity before release.
