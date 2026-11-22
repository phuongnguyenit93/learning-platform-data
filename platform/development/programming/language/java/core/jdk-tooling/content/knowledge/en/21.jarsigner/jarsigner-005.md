# Timestamping JAR Signatures with jarsigner

## Objectives

After this lesson, you will be able to explain timestamps in JAR signatures; understand the role of a Time Stamping Authority (TSA) and the RFC 3161 protocol; distinguish a timestamp from the clock on the signing machine; configure `jarsigner -tsa`, `-tsacert`, `-tsadigestalg`, and `-tsapolicyid`; sign a JAR with a timestamp; verify signatures, timestamps, and certificate chains; handle `noTimestamp` warnings, expired certificates, or invalid TSA chains; and integrate timestamp verification into a release/CI pipeline.

## 1. What is a JAR signature timestamp?

When signing a JAR, `jarsigner` uses the signer's private key to generate a digital signature over the digest information of the entries in the archive. The signature allows recipients to check content integrity and verify the public key corresponding to the signer's certificate.

A **timestamp** is a token signed by a Time Stamping Authority (TSA) to provide evidence that a data value existed at a specific point in time. When signing a JAR with a timestamp, the TSA stamps the signer's digital signature. The timestamp token is stored alongside the signature in the JAR's signature block.

Timestamps are especially useful because code-signing certificates have a limited validity period. If a JAR is signed while the signer's certificate is valid, a trusted timestamp can help the system determine that the signature was created within that validity period, even if the signer certificate expires later.

Without a timestamp, a verifier may not be able to determine whether a signature was created before or after the signer certificate's expiration date, or before/after a future revocation point. The JDK emits a `noTimestamp` warning when a signature does not include a timestamp.

A timestamp does not extend a certificate's validity period, does not make an expired certificate valid for a new signature, and does not automatically bypass revocation status. It provides time evidence that must be evaluated together with the signature, the signer certificate, the TSA certificate, the trust chain, algorithm policies, and revocation information.

## 2. Why is a timestamp needed when signing a JAR?

Suppose a company releases a Java library on March 10. The company's code-signing certificate is valid until June 30. A user downloads the JAR in August.

If the JAR was signed in March and has a valid timestamp from a TSA, the verifier can check that the signature existed while the signer certificate was still valid. Without a timestamp, the verifier may not be able to prove that the signature was created before the certificate expired; the JAR may receive warnings or no longer be accepted under the environment's policy.

A timestamp supports:

- **Proof of existence time:** confirms that the signature existed no later than the time attested by the TSA.
- **Signature verification after signer certificate expiration:** helps verify that the signature was created while the certificate was valid.
- **Release lifecycle management:** preserves time evidence when software is archived, distributed, or verified years later.
- **Revocation point evaluation:** helps determine whether a signature was created before or after a certificate was revoked, when sufficient revocation data and an appropriate verification policy are present.
- **Release policy compliance:** many code-signing workflows require timestamps so artifacts can be verified long-term.

A timestamp does not replace a JAR signature. The signer's signature proves that the data was signed by the corresponding private key; the TSA's timestamp proves that an imprint of the signature was stamped by the TSA at a specific time.

## 3. Role of the Time Stamping Authority

A **TSA (Time Stamping Authority)** is a service that generates and signs timestamp tokens. A TSA must have a reliable time source and a dedicated key for timestamping operations.

In RFC 3161:

1. The client computes a hash (message imprint) of the data to be stamped.
2. The client sends a timestamp request to the TSA.
3. The TSA validates the request and generates a timestamp token.
4. The token contains the message imprint, hash algorithm, `genTime` timestamp, serial number, and policy identifier.
5. The TSA signs the token with a private key dedicated to timestamping.
6. The client verifies the TSA signature, certificate identifier, message imprint, and related fields.

The TSA does not need to receive the entire JAR file or source code to stamp it. The RFC 3161 protocol stamps the hash representing the data. With `jarsigner`, the stamped data is the signer's signature.

The TSA certificate must be suitable for timestamping. Under RFC 3161, a TSA certificate uses the Extended Key Usage (EKU) `id-kp-timeStamping`; this extension must be critical, and the key must be dedicated solely to timestamping operations. A signer certificate used for code signing and a TSA certificate used for timestamping serve two different roles.

### Signing flow diagram

~~~text
JAR entries
    |
    v
jarsigner computes entry digests
    |
    v
Create signature file (.SF)
    |
    v
Signer signs .SF with private key
    |
    v
Signature is sent to TSA via RFC 3161
    |
    v
TSA returns signed timestamp token
    |
    v
jarsigner stores token in signature block
    |
    v
Signed JAR with signature + timestamp
~~~

The timestamp token is stored in the signature block file (for example, `.RSA`, `.DSA`, or `.EC`) alongside the JAR signature. Verifiers do not need a separate external timestamp file outside the JAR if the token has been embedded properly.

## 4. How does RFC 3161 work?

RFC 3161 defines the Time-Stamp Protocol (TSP), including the request and response formats.

### Timestamp request

A request contains:

- Protocol version.
- Message imprint: hash algorithm and hash value.
- Optional Policy OID.
- Optional Nonce to bind the response to the request.
- A flag requesting the TSA to include its certificate in the response.

The client sends the request to the TSA endpoint over a transport supported by the service, typically HTTP(S). RFC 3161 defines MIME types for timestamp requests and responses.

### Timestamp response

A response contains a status and may contain a timestamp token. The token includes time information and the TSA's signature. The client must verify:

- The TSA returned a success status.
- The message imprint in the token matches the data for which timestamping was requested.
- The hash algorithm and hash value are correct.
- The TSA's signature is valid.
- The TSA certificate matches the certificate referenced in the token.
- The token's time and policy match the request.
- The TSA certificate chain is trusted according to policy.
- The TSA certificate status is handled according to the revocation policy.

### A timestamp is not the local clock

The time attested by a TSA is different from the time on the build machine. A local clock can be inaccurate, tampered with, or out of sync. A TSA provides an independent time source and signs with its own private key.

However, timestamp quality depends on the trustworthiness of the TSA, its time source, operational policies, private key protection, and token verification procedures. Merely having a timestamp token does not prove the TSA is trustworthy; the verifier still needs a trust anchor and a policy for accepting the TSA.

## 5. Timestamp syntax in jarsigner

General syntax for signing a JAR:

~~~bash
jarsigner [options] jar-file alias
~~~

Timestamp options:

| Option | Purpose |
|---|---|
| `-tsa url` | Specifies the TSA URL; enables timestamping for the signature |
| `-tsacert alias` | Specifies the TSA certificate in the keystore; the TSA URL is read from the Subject Information Access extension |
| `-tsadigestalg algorithm` | Selects the digest algorithm for the message imprint sent to the TSA |
| `-tsapolicyid policyid` | Sends a policy identifier in OID form to the TSA |

These options are used when signing a JAR. They are not configuration options for `jarsigner -verify`; when verifying, the tool reads the timestamp already stored in the signature block.

### -tsa URL

Example:

~~~bash
jarsigner -tsa https://tsa.example.org app.jar codesign
~~~

The URL must be the timestamp endpoint published by the TSA provider. `tsa.example.org` is only an illustrative placeholder, not an actual TSA service. Replace it with the URL provided by your organization or TSA provider.

When `-tsa` is specified, `jarsigner` sends an RFC 3161 request to that URL. The TSA certificate does not need to be in the keystore just to invoke the `-tsa` option; verification still needs to check the token's trust chain.

If both `-tsa` and `-tsacert` are specified, the URL in `-tsa` overrides the URL found from the `-tsacert` certificate alias.

### -tsacert alias

Example:

~~~bash
jarsigner -tsacert tsa-signing-cert -keystore signing.p12 app.jar codesign
~~~

The alias must identify the TSA's public key certificate in the keystore being used. `jarsigner` reads the Subject Information Access (SIA) extension in the certificate to find the TSA URL.

The TSA certificate must be present in the keystore when using `-tsacert`. If the certificate does not contain the required TSA URL in SIA, this option does not provide enough information to locate the endpoint.

### -tsadigestalg

Example:

~~~bash
jarsigner -tsa https://tsa.example.org -tsadigestalg SHA-384 app.jar codesign
~~~

This option selects the hash algorithm used to create the message imprint sent to the TSA. In JDK 26, if unspecified, the default is SHA-384.

This is the digest for the timestamp request, not the `-digestalg` option used to hash JAR entries, and not `-sigalg` used to sign the signature file.

| Option | Data/Operation |
|---|---|
| `-digestalg` | Digest of entries in the JAR |
| `-sigalg` | Signature algorithm using the signer's private key |
| `-tsadigestalg` | Digest of the message imprint sent to the TSA |

Do not choose an algorithm solely for legacy compatibility. Follow the algorithms supported by the TSA and the security policy of the JDK/publisher.

### -tsapolicyid

Example:

~~~bash
jarsigner -tsa https://tsa.example.org -tsapolicyid 1.2.3.4 app.jar codesign
~~~

The value must be an OID published by the TSA or required by the organization. If omitted, the request does not send a policy OID and the TSA selects its default policy.

Do not invent an arbitrary OID and expect the TSA to accept it. Use the exact policy identifier provided by the TSA provider.

## 6. Preparing the keystore and JAR before signing

To sign a JAR, you need a private key along with its certificate chain in the keystore. The alias passed to `jarsigner` must be the alias of a private-key entry.

Check the alias:

~~~bash
keytool -list -v -keystore signing.p12 -storetype PKCS12 -alias codesign
~~~

Confirm that the entry type is `PrivateKeyEntry`, that the certificate is valid, and that it has appropriate key usage/extended key usage for code signing according to the CA's policy.

If you do not have a JAR yet, create a simple Java program:

~~~text
project/
├── src/
│   └── com/example/Main.java
└── classes/
~~~

File `src/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("signed-jar-ok");
    }
}
~~~

Compile:

~~~bash
javac --release 17 -d classes src/com/example/Main.java
~~~

Create an executable JAR:

~~~bash
jar --create --file app.jar --main-class com.example.Main -C classes .
~~~

Test run before signing:

~~~bash
java -jar app.jar
~~~

Exact output:

~~~text
signed-jar-ok
~~~

Do not modify the JAR contents after signing. If you add, remove, or modify signed entries, digest verification will fail. If you need to modify the artifact, rebuild the JAR and sign it again.

## 7. Signing a JAR with a timestamp using a TSA URL

Suppose:

- Input file is `app.jar`.
- Keystore is `signing.p12`.
- Private key alias is `codesign`.
- The TSA provides its actual endpoint via the `TSA_URL` environment variable.

On Linux/macOS, set the endpoint according to your provider's instructions:

~~~bash
export TSA_URL="https://tsa.your-provider.example/rfc3161"
~~~

Then sign:

~~~bash
jarsigner -keystore signing.p12 -storetype PKCS12 -tsa "$TSA_URL" -tsadigestalg SHA-384 -signedjar app-signed.jar app.jar codesign
~~~

On Windows PowerShell:

~~~powershell
$env:TSA_URL = "https://tsa.your-provider.example/rfc3161"
jarsigner -keystore signing.p12 -storetype PKCS12 -tsa $env:TSA_URL -tsadigestalg SHA-384 -signedjar app-signed.jar app.jar codesign
~~~

Replace the illustrative URL with the real TSA endpoint. When running, keytool/jarsigner may prompt for the store password and private-key password if not already provided.

Explanation:

- `-keystore signing.p12`: selects the keystore containing the private key.
- `-storetype PKCS12`: specifies the keystore format.
- `-tsa "$TSA_URL"`: requests a timestamp from the TSA.
- `-tsadigestalg SHA-384`: selects the hash for the timestamp imprint.
- `-signedjar app-signed.jar`: writes the result to a new file.
- `app.jar codesign`: input JAR and signer alias.

The command succeeds only when the signer key is valid, the TSA endpoint is reachable, the request/response are compatible, and the token is verified and embedded into the signature block. Do not treat the mere creation of the output file as sufficient; always run verification after signing.

### Signing the original file in place

If you omit `-signedjar`, jarsigner overwrites the input file with the signed JAR:

~~~bash
jarsigner -keystore signing.p12 -storetype PKCS12 -tsa "$TSA_URL" -tsadigestalg SHA-384 app.jar codesign
~~~

In release workflows, using a separate output file is usually easier to control because you can keep the unsigned artifact for comparison and publish only the verified file.

## 8. Signing with -tsacert instead of -tsa

If the TSA certificate is already in the keystore and its SIA extension contains the timestamp URL, you can use:

~~~bash
jarsigner -keystore signing.p12 -storetype PKCS12 -tsacert tsa-signing-cert -signedjar app-signed.jar app.jar codesign
~~~

Here:

- `codesign` is the JAR publisher's private key alias.
- `tsa-signing-cert` is the alias of the TSA's public key certificate.
- The URL is retrieved from the Subject Information Access extension of the TSA certificate.

Do not confuse the TSA alias with the signer alias. The two certificates serve two different roles.

If a TSA endpoint is specified with `-tsa`, that URL overrides the URL found from `-tsacert`. Use one clear configuration method to avoid confusion between the certificate and the endpoint.

## 9. Verifying a timestamped JAR

After signing, verify the signature:

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

What to check in the output:

- Each entry is signed and its digest verifies successfully.
- The signature file and signature block are valid.
- The signer certificate and chain are displayed.
- Timestamp information appears in the verbose output if the token is present.
- There are no warnings about an invalid timestamp or an invalid TSA chain.
- There are no warnings about disabled algorithms or signature errors.

To turn severe warnings into errors with a non-zero exit code:

~~~bash
jarsigner -verify -verbose -certs -strict app-signed.jar
~~~

The `-strict` option is very useful in CI because if there are only severe warnings without `-strict`, jarsigner may return exit code 0. With strict enabled, severe warnings are reflected in the exit code.

### Reading the noTimestamp warning

If the JAR does not have a timestamp, jarsigner may emit the warning:

~~~text
This JAR contains signatures that doesn't include a timestamp.
~~~

This warning means a verifier may not be able to verify the JAR after the signer certificate's expiration date or after a future revocation point. For release workflows that require timestamps, this should be treated as an issue to resolve.

### Inspecting certificate details

~~~bash
jarsigner -verify -verbose -certs -strict app-signed.jar
~~~

Read the signer certificate, TSA certificate, and chain details. Do not rely solely on the `jar verified` line. The JDK documentation requires inspecting warnings and certificate contents to decide whether a signature is trustworthy.

### Verifying the signer by alias

If you need to check that the signature was created by a specific alias in a keystore:

~~~bash
jarsigner -verify -keystore trusted-signers.p12 -storetype PKCS12 -verbose -certs -strict app-signed.jar codesign
~~~

The alias after the JAR name is used to match the signer certificate. This checks signer identity against the specified keystore and does not replace checking the TSA's trust policy.

## 10. Timestamp certificate and signer certificate are two different chains

When verifying a timestamped JAR, distinguish at least two roles:

| Component | Function |
|---|---|
| Signer certificate | Authenticates the public key that signed the JAR |
| Signer certificate chain | Links the signer certificate to an accepted trust anchor |
| TSA certificate | Authenticates the signature of the timestamp token |
| TSA certificate chain | Links the TSA certificate to a TSA trust anchor |
| Timestamp token | Binds the signature's message imprint to the time attested by the TSA |

A JAR can have a valid signer signature but an invalid timestamp token, or a valid timestamp token but an untrusted signer certificate chain.

The JDK reports the severe warning `tsaChainNotValidated` when the TSA certificate chain is invalid. There may also be a `hasExpiredTsaCert` warning if the timestamp has expired under current validation.

Therefore, verifying a JAR signature is not just checking a single public key. Both the signer signature and the timestamp token, along with their respective certificate chains, must be evaluated.

## 11. Expired certificates, revocation, and the meaning of timestamps

A timestamp helps prove a signature was created at a point in time, but long-term verification depends on multiple factors.

### Signer certificate expiration

If the timestamp token is valid and the TSA-attested time falls within the signer certificate's validity period, the verifier can evaluate that the signature was created while the certificate was valid.

That does not mean the signer certificate remains valid for signing a new JAR after its expiration date. A timestamp only supports evaluating older signatures.

### Signer certificate revocation

A timestamp can help determine whether a signature predates or postdates a revocation time. However, appropriate revocation information and a verification policy defining how to handle revoked certificates must be available.

If the private key was compromised before the timestamp time, a timestamp alone cannot prove that the legitimate signer created the signature. You must investigate the compromise time, revocation, and PKI evidence.

### TSA certificate expiration or revocation

The TSA certificate also has its own validity period and revocation status. A timestamp token does not automatically become trustworthy just because it is embedded in the JAR. The verifier needs to check the TSA certificate chain, EKU, token signature, time, and policy.

### Weakened or disabled algorithms

The JDK uses security properties such as `jdk.jar.disabledAlgorithms` and `jdk.security.legacyAlgorithms` to evaluate signing/digest algorithms. A disabled algorithm can cause a signature to be treated as unsigned; a legacy algorithm can generate an informational warning.

A timestamp does not make a disabled algorithm secure. Use modern algorithms supported by the JDK, the TSA, and your organization's policy.

## 12. Configuring timestamp policies and algorithms

### Choosing a digest algorithm

JDK 26 uses SHA-384 by default for the timestamp message imprint if `-tsadigestalg` is not specified.

You can specify it explicitly:

~~~bash
jarsigner -tsa "$TSA_URL" -tsadigestalg SHA-384 -signedjar app-signed.jar app.jar codesign
~~~

Only change the algorithm when the TSA supports it and your security policy permits it. Avoid weak digests or those disabled in the JDK.

### Sending a TSA policy OID

If the provider requires a specific policy:

~~~bash
jarsigner -tsa "$TSA_URL" -tsapolicyid 1.2.3.4 -signedjar app-signed.jar app.jar codesign
~~~

The OID in the example is illustrative. Replace it with the official policy identifier provided by the TSA.

### Distinguishing digest, signature, and timestamp digest

A single command can use three different algorithms:

~~~bash
jarsigner -digestalg SHA-384 -sigalg SHA384withRSA -tsadigestalg SHA-384 -tsa "$TSA_URL" -signedjar app-signed.jar app.jar codesign
~~~

- `-digestalg`: hashes the contents of JAR entries.
- `-sigalg`: the signer's signature over the signature file.
- `-tsadigestalg`: hashes the message imprint sent to the TSA.

The choices must be compatible with the key, JDK, TSA, and algorithm policies. You do not need to force all algorithms to be identical if technical requirements do not demand it.

## 13. Integrating timestamps into a CI/CD pipeline

A JAR signing pipeline should separate the build, signing, timestamping, and verification steps:

~~~text
Compile source
      |
      v
Package unsigned JAR
      |
      v
Run unit/integration tests
      |
      v
Sign with code-signing private key
      |
      v
Request RFC 3161 timestamp from TSA
      |
      v
Verify signer signature + timestamp + chains
      |
      v
Run artifact integrity checks
      |
      v
Publish only verified signed JAR
~~~

Implementation principles:

- Use a TSA endpoint approved by your organization.
- Store the signer private key in a secret manager, HSM, or signing service.
- Do not write store passwords/key passwords into source control or logs.
- Use a reliable TSA endpoint and monitor its availability.
- Configure timeouts/retries at the pipeline layer according to policy; do not publish the artifact if the timestamp request fails.
- Retain unsigned and signed JARs according to artifact retention rules.
- Verify using a supported JDK in the release environment.
- Use `-strict` so severe warnings fail the job.
- Retain signing/verification logs, certificate fingerprints, TSA policy OIDs, and artifact checksums.
- Do not treat a timestamp token as the sole proof of the publisher's identity.

### Example signing and verification steps in CI

The following commands assume CI has provided `TSA_URL` and the signer keystore via secret management:

~~~bash
jarsigner -keystore signing.p12 -storetype PKCS12 \
  -tsa "$TSA_URL" -tsadigestalg SHA-384 \
  -signedjar build/app-signed.jar build/app.jar codesign

jarsigner -verify -verbose -certs -strict build/app-signed.jar
~~~

The pipeline should publish `build/app-signed.jar` only if both signing and verification succeed, and all other policy checks also pass.

Do not pass real passwords via command-line arguments if the environment may record process arguments or shell history. Use prompts, an HSM/token, or a CI-protected secret mechanism.

## 14. Timestamps when a JAR has multiple signatures

A JAR can be signed by multiple signers. Each time it is signed, jarsigner creates a new pair of signature file and signature block for that signer.

If each signer uses a timestamp, each signature can have its own timestamp token. When verifying, check each signer and its corresponding token; do not assume one timestamp applies to all signatures.

Example:

~~~bash
jarsigner -tsa "$TSA_URL" -signedjar signed-by-alice.jar app.jar alice
jarsigner -tsa "$TSA_URL" signed-by-alice.jar bob
~~~

The second command adds another signature to the already signed JAR. Adding a new signature updates manifest/signature metadata according to JAR signing rules; the earlier signature can still verify as long as previously signed entries were not modified.

If entry contents change, you must rebuild and re-sign the artifact. Do not use post-signing JAR editing as a way to update contents.

## 15. Common errors and troubleshooting

### TSA URL is unreachable

**Symptom:** jarsigner reports a connection error or receives no timestamp response.

**Cause:** wrong URL, DNS/network/proxy error, TSA outage, or the endpoint does not support RFC 3161.

**Resolution:** verify the endpoint with the provider; check DNS, proxy, firewall, and TLS; retry in an authorized environment. Do not release the JAR as if timestamping succeeded.

### TSA rejects the request

**Symptom:** TSA response has an error status or contains no token.

**Cause:** unsupported digest algorithm, invalid policy OID, incompatible request format, or the client is not authorized to use the service.

**Resolution:** check the TSA policy, supported algorithms, account/entitlement, and request configuration. Omit `-tsapolicyid` only when the provider confirms the default policy is acceptable.

### Wrong -tsacert alias

**Symptom:** jarsigner cannot find the TSA URL or cannot find the certificate alias.

**Cause:** alias does not exist in the keystore, the certificate lacks an appropriate SIA URL, or the alias points to the signer certificate by mistake.

**Resolution:** inspect aliases with `keytool -list -v`; verify the TSA certificate and Subject Information Access extension; use `-tsa` if you want to specify the endpoint directly.

### Invalid timestamp token

**Symptom:** verification reports an invalid timestamp or an unvalidated TSA chain.

**Cause:** invalid token signature, mismatched message imprint, untrusted TSA certificate, or incomplete TSA chain.

**Resolution:** re-sign with an approved TSA endpoint; check the TSA's trust anchors/intermediate certificates; verify that the TSA certificate has the appropriate timestamping EKU.

### Expired TSA certificate

**Symptom:** `hasExpiredTsaCert` warning.

**Cause:** the TSA certificate is no longer within its validity period during verification.

**Resolution:** check the timestamp token, TSA chain, and long-term verification policy. Do not ignore the warning if the release process requires a valid timestamp; contact the TSA provider to confirm service and certificate status.

### TSA chain not validated

**Symptom:** `tsaChainNotValidated` severe warning.

**Cause:** missing intermediate/root certificate, untrusted TSA certificate, or chain error.

**Resolution:** verify the trust anchor and TSA certificate chain from an official source; check the verification environment's trust policy. Do not add unknown certificates to the truststore just to suppress the warning.

### JAR has no timestamp

**Symptom:** `noTimestamp` warning.

**Cause:** the JAR was signed without specifying `-tsa` or `-tsacert`, or the TSA request failed and the signature does not contain a valid timestamp.

**Resolution:** inspect the signing command and output; re-sign from the unsigned JAR using a verified TSA endpoint. Do not attempt to add a timestamp by manually editing the signature block.

### JAR verifies successfully yet CI does not fail

**Symptom:** logs show a severe warning but the job exit code is 0.

**Cause:** jarsigner was not invoked with `-strict`. Without strict, severe warnings may not produce a non-zero exit code.

**Resolution:** add `-strict` to the verify command and check the exit code in the pipeline.

### Expired signer certificate

**Symptom:** `hasExpiredCert` warning or the signature is rejected by policy.

**Cause:** the signer certificate has expired and the timestamp is missing, invalid, or falls outside the signer certificate's validity period.

**Resolution:** verify the timestamp token, TSA time, and signer chain; check revocation information. If the signature was created after the certificate expired, a new certificate must be issued and the artifact re-signed.

### Disabled signing algorithm

**Symptom:** `disabledAlg` warning or the signature is treated as unsigned.

**Cause:** the digest/signature algorithm or key size is no longer accepted by the JDK's security properties.

**Resolution:** use modern algorithms and key sizes per JDK/TSA policy; re-sign the artifact. Do not weaken the security policy just to make verification pass.

## 16. Pre-release checklist for a timestamped JAR

### Before signing

- [ ] JAR is built/tested and its contents will no longer change.
- [ ] Signer alias points to the correct `PrivateKeyEntry`.
- [ ] Signer certificate is valid at signing time.
- [ ] Signer certificate chain is trusted by the organization.
- [ ] Key usage/extended key usage permits code signing.
- [ ] TSA endpoint is obtained from a trusted provider.
- [ ] TSA policy OID and digest algorithm are appropriate.
- [ ] Private key is protected by an HSM/secret manager or secure mechanism.

### After signing

- [ ] Output JAR is the intended artifact.
- [ ] Signature file and signature block exist in `META-INF`.
- [ ] Timestamp token is embedded in the signature block.
- [ ] `jarsigner -verify -verbose -certs -strict` succeeds.
- [ ] Signer signature and certificate chain are verified.
- [ ] TSA token and TSA certificate chain are verified.
- [ ] No `noTimestamp`, `tsaChainNotValidated`, `hasExpiredTsaCert`, or unresolved severe warnings.
- [ ] Revocation policy has been evaluated appropriately.
- [ ] Artifact checksum, signing logs, and verification logs are retained.
- [ ] Only the verified artifact is published.

## 17. Official references

- [The jarsigner Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html) — `-tsa`, `-tsacert`, `-tsadigestalg`, `-tsapolicyid` options; how timestamp tokens are embedded; verification and warning codes.
- [RFC 3161 — Internet X.509 Public Key Infrastructure Time-Stamp Protocol](https://www.rfc-editor.org/rfc/rfc3161.html) — request/response, message imprint, timestamp token, TSA certificate, and security requirements.
- [Java Security Standard Algorithm Names — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html) — standard names for digest and signature algorithms.
- [Java KeyStore API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html) — keystore, private-key entry, and certificate chain.
- [JAR File Specification — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html) — manifest, signature file, and signed JAR structure.

Timestamps preserve evidence that a JAR signature existed at a time attested by a TSA. Use a trusted TSA, choose appropriate algorithms and policies, and verify both the signer and TSA chains with `jarsigner -strict` before releasing.