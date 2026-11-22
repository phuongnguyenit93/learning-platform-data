# Algorithms and Key Sizes That Are No Longer Accepted

During a **Java Advance Compatibility Migration**, an application may compile successfully and start up normally yet still fail when establishing an HTTPS connection, validating a certificate chain, verifying a JAR signature, or performing cryptographic operations with keys generated years earlier. The cause is not necessarily a removed Java API. Certain **algorithms, protocols, or key sizes are no longer accepted by the JDK security policy in that specific usage context**.

These restrictions are intentional safety measures. The right resolution is not removing all security constraints so the program runs as before, but identifying which policy rejected the operation, replacing the unsuitable certificate/key/protocol, and re-testing on the target runtime.

This lesson explains how the JDK manages algorithms and key lengths, the intersections among TLS, PKIX, JAR signing, and JCA/JCE, how to diagnose different errors, and a migration process that preserves security.

## 1. Why Does Changing the JDK Break Cryptographic Operations?

The outcome of a security operation depends on multiple layers:

- **JDK vendor and release/update:** default configurations can change even between patch updates within the same LTS line.
- **Security provider:** SunJSSE, SunEC, SunRsaSign, or an external/HSM provider determines which algorithms are implemented.
- **Security properties:** an algorithm may be disabled or constrained by usage purpose and key size.
- **Certificate chain and key material:** certificates may have weak signatures, short keys, be expired, or lack a trust anchor.
- **The remote peer of the connection:** an old server, load balancer, API gateway, network device, or legacy client may support only obsolete protocols/ciphers.
- **Runtime packaging:** custom images, truststores, modules, PKCS#11 providers, and native libraries may differ between build and production.

For example: a legacy Java client previously communicated with a device accepting only TLS 1.0. When a newer JDK disallows that protocol, the application call remains unchanged yet the handshake fails. Or a server still uses a 1024-bit RSA certificate, causing a newer client to reject the certificate path under the active policy.

**Do not infer security policy solely from the JDK version name.** Algorithm deprecation/disabling milestones may be introduced in updates to JDK 8, 11, 17, and other releases; vendors may also customize defaults.

## 2. Easily Confused Terms

| Component | Examples | Meaning |
|---|---|---|
| Protocol | SSLv3, TLS 1.0, TLS 1.1, TLS 1.2, TLS 1.3 | Both sides must negotiate an allowed version |
| Cipher suite | TLS suites using AES-GCM, ChaCha20-Poly1305, or legacy algorithms | Must be accepted by both sides and the security policy |
| Public-key algorithm | RSA, DSA, EC | Defines the key and signature scheme |
| Key size | RSA 1024/2048/3072-bit, EC P-256 | Failing policy minimums can cause verification/signing failures |
| Signature algorithm | SHA1withRSA, SHA256withRSA, SHA384withECDSA | Binds a digest with a signature mechanism |
| Digest/hash | SHA-1, SHA-256, SHA-384 | Availability in an API does not mean permission in certificates/JARs |
| Symmetric cipher | AES, 3DES, RC4 | Mode/key size/algorithm may no longer meet standards |
| Security provider | SunJSSE, SunRsaSign, SunEC, PKCS#11 | Provides implementations and corresponding capabilities |

### 2.1. Do Not Compare Bit Lengths Across Different Algorithm Families

A 256-bit RSA key, 256-bit AES key, and EC P-256 key do not offer the same security level merely because all contain the number 256.

- 1024-bit RSA is considered weak for many modern purposes.
- 2048-bit RSA is a common baseline threshold, though some policies require higher strength or shorter lifetimes.
- 3072-bit RSA may be suitable when longer-term protection is needed, depending on cost and interoperability.
- P-256/P-384 belong to elliptic-curve cryptography and must be evaluated according to that cryptosystem's properties.
- 128/256-bit AES is evaluated under the symmetric cryptography model.

Choose keys based on organizational security requirements, applicable standards, and support across HSMs, servers, clients, and certificate authorities (CAs), rather than relying on a single absolute number.

### 2.2. Disallowed Algorithms Differ from Missing Algorithms

`NoSuchAlgorithmException` typically relates to an incorrect algorithm name or a provider lacking a matching implementation. By contrast, a message such as `Algorithm constraints check failed` indicates that an operation is blocked by a context-specific policy constraint.

`InvalidKeyException` can also arise due to invalid keys/parameters, disallowed key sizes, lack of provider support, or JCE rules. Do not treat all of them by simply adding provider JARs.

## 3. JDK Security Properties

Modern JDKs include a `java.security` configuration file, typically in the `conf/security` directory of the JDK/runtime image. Paths and values must be verified on the running JDK release.

| Security property | Typical Scope |
|---|---|
| `jdk.tls.disabledAlgorithms` | TLS/JSSE algorithms, protocols, and constraints |
| `jdk.certpath.disabledAlgorithms` | Algorithm and key-size constraints when validating certificate paths |
| `jdk.jar.disabledAlgorithms` | Constraints in JAR signature verification |
| `jdk.security.legacyAlgorithms` | Algorithms considered legacy in certain tools; does not mean banned in every context |
| `crypto.policy` | JCE cryptographic strength policy, distinct from disabled algorithms above |

Values can contain algorithm names and conditions, for example in illustrative syntax:

```text
RSA keySize < 2048
```

This is **not a claim that every JDK 17 defaults to this threshold**. Certain rules also depend on usage purpose, trust anchor conditions, or cutoff dates. Always inspect the actual policy.

### 3.1. Reading the Active Policy

```java
import java.security.Security;

public final class SecurityPolicySnapshot {
    public static void main(String[] args) {
        print("jdk.tls.disabledAlgorithms");
        print("jdk.certpath.disabledAlgorithms");
        print("jdk.jar.disabledAlgorithms");
        print("jdk.security.legacyAlgorithms");
        print("crypto.policy");
    }

    private static void print(String name) {
        System.out.println(name + " = " + Security.getProperty(name));
    }
}
```

Run with the application's exact JDK:

```bash
javac SecurityPolicySnapshot.java
java SecurityPolicySnapshot
```

Save the snapshot alongside vendor, full version, runtime image, and deployment environment metadata to compare before and after migration.

### 3.2. `disabledAlgorithms` Does Not Mean an Absolute Ban Across All APIs

`MessageDigest.getInstance("SHA-1")` may still locate a SHA-1 implementation, while the certificate path validator rejects a SHA-1 signature under its own rules. Similarly, JCA may support RSA while an overly short RSA certificate is rejected in TLS.

**Algorithm availability** (having an implementation) differs from **algorithm acceptability** (being permitted by policy in a specific security flow). Checking provider support does not replace testing PKIX, TLS, or JAR signing.

### 3.3. Do Not Edit the Global Security File to Bypass an Error

Modifying security properties in a JDK image can affect every application sharing that runtime. Disabling constraints globally so a legacy endpoint can connect widens risk across all other endpoints.

The goal is replacing obsolete protocols, certificates, keys, or peer systems. Any unavoidable exception must have an owner, risk assessment, isolated scope, and removal deadline.

## 4. TLS Protocols That Are No Longer Accepted

### 4.1. TLS 1.0 and TLS 1.1

TLS 1.0 and TLS 1.1 are obsolete. Newer JDK updates disable them by default in many JSSE configurations. In migration planning, prioritize TLS 1.2 or TLS 1.3.

If the server supports only an older protocol, the application may report:

```text
javax.net.ssl.SSLHandshakeException:
  Received fatal alert: protocol_version
```

or:

```text
No appropriate protocol
(protocol is disabled or cipher suites are inappropriate)
```

These messages are not enough to pinpoint the full root cause: you also need to inspect the protocols offered by both sides, cipher suites, security policy, and intermediary network devices.

### 4.2. Cipher Suites Must Also Be Compatible

Two peers both supporting TLS 1.2 can still fail the handshake if they share no mutually accepted cipher suite. Legacy devices supporting only RC4, 3DES, or obsolete key exchanges may not interoperate with a newer JDK client.

Modern choices often use AEAD suites such as AES-GCM or ChaCha20-Poly1305, though the actual cipher suite also depends on the protocol, provider, compliance policy, and hardware.

Do not assume a broader cipher suite list is automatically better; the goal is a **secure and interoperable selection**.

### 4.3. Enabling a Protocol in Code Alone Is Insufficient

```java
sslSocket.setEnabledProtocols(new String[] {"TLSv1.2"});
```

This setting does not override constraints in `jdk.tls.disabledAlgorithms`. Likewise, requesting a cipher suite does not mean the runtime will use it if the provider or security policy rejects it.

### 4.4. mTLS Faces Bidirectional Constraints

With mutual TLS, both the server and client require compliant certificates/keys. A client certificate with a disallowed signature algorithm or key size can fail the handshake even if the server certificate meets standards.

When upgrading the JDK, check both directions:

- Server certificate/key.
- Client certificate/key.
- CAs and truststores on both sides.
- Key usage, extended key usage, and certificate aliases.
- Signature schemes, supported groups, and cipher suites.

## 5. Certificate Path Validation and Key Length

### 5.1. Validate the Entire Chain, Not Just the Leaf

```text
Leaf certificate (api.example.com)
       |
       v
Intermediate CA
       |
       v
Root CA / trust anchor
```

A new leaf certificate with a strong key can still fail if an intermediate CA uses a weak signature algorithm, depending on the exact constraints.

Messages may include:

```text
javax.net.ssl.SSLHandshakeException:
  PKIX path validation failed
```

and deeper:

```text
java.security.cert.CertPathValidatorException:
  Algorithm constraints check failed ...
```

Read the nested causes and check which part of the chain was actually rejected.

### 5.2. Context-Dependent Restrictions on SHA-1

SHA-1 is no longer suitable for many new signing purposes. However, constraints in `jdk.certpath.disabledAlgorithms` may apply specific conditions involving trust anchors or usage. Do not claim every SHA-1 certificate is unconditionally rejected in every Java 17 environment.

Inspect:

1. Signature algorithms of the leaf and intermediates.
2. Public key algorithm/key size of each certificate.
3. Trust anchor and certificate usage.
4. Policy values on the target JDK.
5. Full exception chain during validation.

The long-term goal is reissuing certificate chains that satisfy organizational policy and client interoperability.

### 5.3. A Truststore Does Not Override Policy

Importing a certificate into a truststore does not automatically make its algorithm or key size compliant. Trust decisions and algorithm constraints are separate control layers.

Errors to distinguish:

- Untrusted CA.
- Server omits an intermediate certificate.
- Expired or not-yet-valid certificate.
- Subject Alternative Name does not match the hostname.
- Certificate/key usage does not match the intended purpose.
- Algorithm or key size violates policy.

Changing key size will not fix a hostname mismatch; adding a trust anchor will not necessarily resolve an algorithm constraint.

## 6. RSA, DSA, and EC: Key Size Must Fit Each Algorithm Family

### 6.1. 1024-Bit RSA in Legacy Systems

1024-bit RSA commonly appears in certificates/keystores created years ago, such as internal servers, gateway appliances, mTLS clients, JAR signers, or unrotated HSM tokens.

Under many modern policies, this key fails the threshold. The fix is to **generate a new key pair and reissue the certificate**, not tweak a metadata attribute.

The process includes identifying the owner, selecting the key algorithm/size, generating new keys in a secure store, requesting a new certificate from the CA, deploying the full chain, and testing all supported clients.

### 6.2. RSA 2048/3072 or ECDSA

Common strategies:

- 2048-bit RSA where policies allow and lifetimes are appropriate.
- 3072-bit RSA when greater security margin is needed, subject to interoperability.
- ECDSA on a widely supported named curve such as P-256/P-384, if server/client/HSM and the certificate chain support it.

Do not switch from RSA to ECDSA merely by altering JDK configuration; update keys, certificates, signature schemes, the TLS stack, and test legacy clients.

### 6.3. DSA and Provider Differences

Some older applications use DSA or specialized providers. Check the algorithm type, key size, parameters, and usage context. An algorithm may still be implemented yet unsuitable for signing new certificates.

HSM/PKCS#11 setups also depend on native drivers, token policies, and signing mechanisms supported by the hardware. Testing with a software provider on a laptop does not prove production HSM compatibility.

### 6.4. AES/JCE Policy Is a Separate Topic

Historical JDKs imposed JCE cryptographic strength limits in certain configurations. Modern JDKs typically support strong cryptography more broadly; when encountering `InvalidKeyException: Illegal key size`, inspect `crypto.policy`, the provider, and the actual runtime.

AES-256 should not be evaluated by the same bit numbers or constraints as 2048-bit RSA. Never shorten keys or switch to a weaker algorithm before identifying the real error.

## 7. JAR Signatures and `jdk.jar.disabledAlgorithms`

A JAR may have been signed long ago using an obsolete digest or signature algorithm. When upgrading the JDK, verification tools may warn about or treat signatures that no longer meet policy accordingly.

### 7.1. Verifying JARs

```bash
jarsigner -verify -verbose -certs release.jar
```

In CI you can use:

```bash
jarsigner -verify -strict -verbose -certs release.jar
```

Check both the exit code and output, including warnings about weak algorithms, signer certificates, timestamps, key sizes, or chains. Do not just look for the string “jar verified” while ignoring meaningful warnings.

### 7.2. Re-Releasing with Compliant Signatures

Example syntax for signing a JAR with a valid RSA private key:

```bash
jarsigner \
  -keystore signer.p12 \
  -storetype PKCS12 \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  -signedjar release-signed.jar \
  release.jar signer
```

The command assumes `signer.p12` contains the alias `signer` and a matching private key/certificate. This is not a complete production signing workflow; protect keys and passwords using organization-approved secret management.

If the product requires verification after the signer certificate expires, timestamping and signature-evidence retention policies can be critical.

### 7.3. Re-Signing Artifacts of Unknown Provenance Is a Risk

Do not simply download a JAR from an arbitrary source and re-sign it to silence a warning. Verify provenance of the source code, dependencies, and build pipeline before issuing a new signature.

JAR signature verification is one piece of supply-chain security; it does not replace HTTPS, repository access control, or checksum validation.

## 8. JCA/JCE Cryptographic APIs and Security Providers

JCA/JCE provides APIs such as `KeyPairGenerator`, `Signature`, `Cipher`, and `MessageDigest`. A provider may support an operation directly while TLS, the certificate validator, or the JAR verifier enforces stricter policies.

Illustrative signature-generation example:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public final class SignExample {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair pair = generator.generateKeyPair();

        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(pair.getPrivate());
        signature.update("payload".getBytes(StandardCharsets.UTF_8));

        byte[] signed = signature.sign();
        System.out.println("Signature length: " + signed.length);
    }
}
```

The example above is **not a production key-management workflow**. A business signing system requires stable policy-compliant private keys protected via keystore/KMS/HSM, auditing, and rotation.

Do not use a successful `Signature.getInstance(...)` call as proof that a TLS or JAR certificate will be accepted.

### 8.1. Providers Can Vary Across JDKs

An older provider may support a curve or alias that a newer provider no longer offers. An HSM may lack signature schemes needed for modern TLS. A custom `jlink` image may also omit required modules or providers.

Therefore, testing must cover the exact runtime image and target hardware or provider, not just a full JDK on a developer workstation.

## 9. Diagnosing on the Actual Runtime

### 9.1. Identifying the Exact JDK

```bash
java -version
java --list-modules
```

Record the vendor, full update version, architecture, and container image. The Gradle daemon, forked test JVMs, application server, and desktop client may all run on different JDKs.

### 9.2. Inspecting Certificates

For a certificate file:

```bash
keytool -printcert -file server.crt
```

For a TLS server:

```bash
keytool -printcert -sslserver api.example.com:443
```

For a keystore:

```bash
keytool -list -v \
  -keystore server-keystore.p12 \
  -storetype PKCS12
```

Do not pass keystore passwords on the command line or commit them to a repository. The tool can prompt for the password interactively.

Inspect the issuer, subject/SAN, validity, public key algorithm/size, signature algorithm, chain, alias, and trust anchor.

### 9.3. Enabling Logging in a Controlled Manner

```bash
java -Djavax.net.debug=ssl:handshake -jar app.jar
```

If certificate path details are needed:

```bash
java -Djava.security.debug=certpath \
  -Djavax.net.debug=ssl:handshake \
  -jar app.jar
```

Logs can be huge and contain sensitive operational details. Enable them only in appropriate environments and protect the output.

### 9.4. Distinguishing Exceptions

| Symptom | Possible Cause | Investigation Steps |
|---|---|---|
| `SSLHandshakeException: protocol_version` | No mutually supported protocol | Check TLS versions and JSSE policy |
| `No appropriate protocol` | Protocols/ciphers disabled | Check `jdk.tls.disabledAlgorithms` and both endpoints |
| `PKIX path validation failed` | Chain/truststore/expiry/constraints | Read nested causes |
| `Algorithm constraints check failed` | Signature/key size fails policy | Identify the exact property and certificate |
| `InvalidKeyException` | Incompatible key/parameters/provider/policy | Inspect JCE, key, and provider |
| `NoSuchAlgorithmException` | Provider/algorithm unavailable | Check algorithm name and implementation |
| JAR signer warning | Non-compliant digest/signature/key | Run `jarsigner -verify -strict` |
| mTLS failure | Incompatible client certificate/key/usage | Inspect the chain in both directions |

A single exception cannot replace a thorough analysis of the security policy and stack trace.

## 10. Scenario 1: Server Supports Only Legacy TLS

```text
New Java application
       |
       | TLS handshake
       v
Legacy server: TLS 1.0 only
```

Action plan:

1. Verify that the server genuinely supports only legacy protocols/ciphers.
2. Upgrade the server, TLS library, or reverse proxy to support TLS 1.2/1.3 and approved ciphers.
3. Inspect certificates/keys and chains during the same upgrade.
4. Re-run integration tests on the target JDK.
5. If an appliance cannot be upgraded immediately, evaluate an isolated, monitored integration gateway with a replacement deadline.

**Do not re-enable TLS 1.0 or weak ciphers across the entire JVM for a single outdated peer.** A gateway, if used, only confines the exposure zone rather than making the legacy connection secure.

## 11. Scenario 2: 1024-Bit RSA Certificate

Suppose a server uses 1024-bit RSA and is rejected by the target client runtime under security policy. Re-importing the certificate into the truststore will not necessarily fix the algorithm constraint.

Steps:

1. Identify the owner, private key location, and legacy certificate chain.
2. Choose the new algorithm/key size per policy and interoperability requirements.
3. Generate a new key pair in a managed keystore/HSM.
4. Generate a CSR and request a new certificate from the appropriate CA.
5. Configure SANs, key usage, extended key usage, and the full chain properly.
6. Roll out, test TLS/mTLS, and rotate/revoke old keys.

Example generating an RSA key in a test keystore:

```bash
keytool -genkeypair \
  -alias app-server \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -storetype PKCS12 \
  -keystore server-keystore.p12 \
  -validity 365
```

The command above generates a key pair and self-signed certificate per `keytool` behavior; **self-signed certificates are not trusted by production clients by default**. A CSR and proper CA workflow are required:

```bash
keytool -certreq \
  -alias app-server \
  -keystore server-keystore.p12 \
  -storetype PKCS12 \
  -file app-server.csr
```

Do not store private keys or passwords in source code, scripts, or logs.

## 12. Scenario 3: JAR Signed with a Legacy Algorithm

An old artifact has a SHA-1 signature or weak signer key. Newer runtimes/tools warn that the signature no longer satisfies policy.

How to handle it:

1. Preserve the original artifact, checksum, and provenance.
2. Verify using `jarsigner -verify -strict -verbose -certs`.
3. Identify the algorithm, digest, key size, signer chain, and timestamp.
4. Rebuild from trusted source.
5. Sign with a compliant key/certificate and timestamp where needed.
6. Verify the released artifact on the actual consumer runtime.

Do not simply re-sign a JAR of unknown origin to bypass a warning.

## 13. Scenario 4: Data Encrypted with an Obsolete Algorithm

An application may still store data encrypted with 3DES or an unauthenticated mode. Simply changing the algorithm name in `Cipher.getInstance(...)` will not make old ciphertext readable by the new algorithm.

Design format versioning:

```text
Legacy data v1
       |
       v
Controlled decryption (if policy allows)
       |
       v
Verify integrity and metadata
       |
       v
Re-encrypt with new v2 format/key
       |
       v
Verify and then stop writing v1 format
```

The migration must manage key rotation, IVs/nonces, authentication tags, batch recovery, and rollback. If switching to AES-GCM, **never reuse a nonce with the same key**.

The system must distinguish reading historical data under a migration workflow from continuing to write new data using weak algorithms.

## 14. Changes Can Also Come from JDK Patch Updates

When Java 17 updates to a newer 17.x release, security defaults can change even when source code and dependencies do not change.

Therefore, compare:

- Full JDK vendor/version.
- `java.security` and security properties.
- Installed providers and provider order.
- Actual key/certificate material.
- Server/client TLS stacks.
- Runtime image and container digest.
- Native/HSM/PKCS#11 components.

If a browser accesses a page successfully while a Java client fails, remember that browsers and the JVM may use different truststores and validators. Testing must use the deployed Java runtime.

## 15. Do Not Lower Security Standards for a “Quick Fix”

Practices to avoid:

- Disabling hostname verification.
- Writing a `TrustManager` that trusts all certificates.
- Enabling TLS 1.0 or weak ciphers across the entire server/runtime.
- Lowering key-size constraints globally.
- Switching to overly short keys because legacy hardware cannot handle stronger algorithms.
- Placing private keys/passwords in source code or CI logs.
- Re-signing artifacts without provenance.
- Keeping security exceptions indefinitely.

If a legacy device cannot be replaced immediately, establish a risk assessment, network/process segmentation, an owner, monitoring, and a decommissioning deadline. That is a controlled transitional measure, not a new security baseline.

## 16. Overall Migration Process

### Step 1: Inventory

List all TLS/mTLS endpoints, keystores, truststores, certificate chains, JAR signing keys, HSMs, providers, and cryptographic APIs in use.

### Step 2: Capture a Baseline

Record JDK vendor/update, a security property snapshot, certificate metadata, TLS test results, and current JAR verification output.

### Step 3: Run on the Target JDK

Run integration tests on the new JDK with initial security defaults; capture exception chains and logs from the exact failing JVM.

### Step 4: Classify

Determine whether the failure stems from protocol, cipher, truststore, certificate signature/key size, missing provider, JCE limit, mTLS, or an unrelated application bug.

### Step 5: Replace the Right Component

Upgrade the server's TLS stack; reissue certificates/keys; upgrade providers/HSMs; re-sign JARs compliantly; or build a safe migration path for legacy data.

### Step 6: End-to-End Testing

Test with certificates, truststores, runtime images, containers, and endpoints closely matching production. Test certificate rotation, key rollover, and remaining client versions.

### Step 7: Monitored Release

Roll out in phases, monitoring handshake failures, certificate validation errors, signer warnings, and provider errors. Record versions and active policies in release records for troubleshooting.

### Step 8: Retire Legacy Artifacts

Revoke weak keys/certificates, remove temporary exceptions, update CI checks for key size/algorithms, and schedule periodic security patch reviews.

## 17. Checklist Before Accepting a Migration

- [ ] Identified the exact JDK vendor, full update version, and runtime image.
- [ ] Read `jdk.tls.disabledAlgorithms`, `jdk.certpath.disabledAlgorithms`, and `jdk.jar.disabledAlgorithms`.
- [ ] Distinguished provider availability errors from security policy errors.
- [ ] Inventoried TLS versions and cipher suites on both ends.
- [ ] Inspected public key algorithms/key sizes/curves of leaf and intermediate certificates.
- [ ] Verified signatures, SANs, trust anchors, expiration, key usage, and EKU.
- [ ] Checked client certificates as well where mTLS is used.
- [ ] Used `jarsigner -verify -strict` where JAR signing applies.
- [ ] Inspected `crypto.policy` if encountering JCE key-size issues.
- [ ] Tested the corresponding HSM/PKCS#11/native providers.
- [ ] Selected new algorithms/keys conforming to organizational policy.
- [ ] Ran tests against the final runtime, truststore, and endpoints.
- [ ] Established rotation, rollback, expiry alert, and monitoring plans.
- [ ] Checked policy changes introduced by JDK updates.
- [ ] Removed or placed time-bound controls on legacy exceptions.

## 18. Conclusion

In Java Compatibility Migration, an algorithm or key size that worked previously is not guaranteed to remain accepted by the JDK forever. TLS/JSSE, PKIX certificate path validation, JAR signing, and JCA/JCE enforce distinct policies, while security providers and JDK updates can alter outcomes without any change to source code.

For a sustainable migration, **read the active security policy accurately, identify the rejected context, replace weak keys/certificates/protocols, and test in the final deployment environment**. The goal is preserving functionality while raising security standards, rather than restoring risky cryptographic configurations just to get past startup errors.
