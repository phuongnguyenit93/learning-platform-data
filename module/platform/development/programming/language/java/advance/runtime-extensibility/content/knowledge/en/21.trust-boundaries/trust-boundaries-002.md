# Distinguishing Integrity Checks, Signatures, and Publisher Trust

In a Java runtime-extensibility architecture, plugins may be downloaded from artifact repositories, mirrors, the Internet, or partner-supplied directories. The fact that a **plugin.jar file downloaded successfully**, or even that a file **carries a valid cryptographic signature**, is not sufficient grounds for the host to load classes and execute them. The host must distinguish three questions:

1. **Integrity:** Do the JAR's bytes match the approved artifact, verified against an independent and trusted reference source, or were they modified?
2. **Digital signature:** Does the file or release metadata have a valid signature under a specific public key? Was the corresponding private key used to sign the data within the signature's scope?
3. **Publisher trust / authorization:** Does that verified key, certificate, or identity actually belong to a publisher authorized by the **host** to release this exact plugin?

**A valid signature made with an unknown key is still a valid signature, yet it establishes no trust in the publisher.** A SHA-256 hash that matches a value just downloaded from the same untrusted source may fail to prevent substitution. Even an artifact from an authorized vendor, properly signed, can contain bugs or dangerous code; artifact verification **is not an execution sandbox**.

This lesson focuses on the trust boundary between a Java host and external plugins. We examine SHA-256, Ed25519, pinning, X.509, the signed JAR mechanism with `jarsigner`, loading and verifying before `ClassLoader`/`ServiceLoader`, and a runnable Java 17+ example.

## 1. The Three-Layer Model: integrity → signature → authorization

| Layer | Operation | If it succeeds, what can we say? | What we cannot yet claim |
| --- | --- | --- | --- |
| **Integrity** | Compute SHA-256 of the artifact and compare against a protected expected digest | The received bytes match the version identified by the digest | Who published that version or whether it is safe |
| **Signature** | Verify the signature over the exact data using the corresponding public key | The data has not changed within the signature's scope and the signature is valid for the tested key | Whether the public key belongs to an authorized publisher |
| **Publisher trust** | Check trusted key/certificate, identity, plugin ID/version scope, and revocation policy | An authenticated entity is authorized to supply that release under the host's policy | That the code will not cause harm once executed |

Examples:

- A JAR file is modified after signing while keeping the old signature: the signature will not match the data. This is **SIGNATURE_INVALID**.
- An attacker generates their own keypair, signs their JAR, and distributes their public key alongside it: `Signature.verify` may return `true`, yet it is **SIGNER_NOT_TRUSTED**.
- Publisher A is authorized to sign plugin A but attempts to distribute plugin B's ID: A's identity may authenticate cleanly, yet it is **PUBLISHER_NOT_AUTHORIZED** for plugin B.
- An authorized publisher signs a release containing a vulnerability: all three layers may pass, so review, update, privilege-restriction, and release-revocation policies are still needed.

Do not collapse every outcome into a single Boolean named `isValid` with no explanation. A real-world verifier typically needs to distinguish results such as **hashMismatch**, **signatureInvalid**, **unknownSigner**, **certificateInvalid**, **releaseNotAllowed**, and **verified**. These names are application-design examples, not JDK enums.

## 2. Threat Analysis at the Plugin Boundary

A typical plugin loading flow looks like this:

~~~text
Publisher / repository / CDN
             |
             | download JAR + metadata / signature
             v
      Untrusted staging area
             |
             | integrity, signature, signer trust,
             | authorization, dependency digests
             v
    Verified immutable artifact
             |
             | create ClassLoader / ModuleLayer
             v
      ServiceLoader / instantiate
             |
             | prepare / activate
             v
          Runtime plugin
~~~

Different attack points:

1. **Modifying files in transit or in the repository:** trusted checksums and signatures detect differences from the accepted release.
2. **Replacing both the file and the checksum:** if both come from an unprotected location, an attacker can generate a new checksum. A chain of trust is needed for the **expected checksum value**.
3. **Impersonating a publisher:** a signature made with a self-generated key still verifies successfully. A trust anchor, pinned key, or certificate chain plus publisher policy is required.
4. **Using a valid certificate outside its scope:** a publisher may be authorized to sign one product, not a different plugin ID.
5. **Replacing the file after verification:** an attacker swaps the JAR at the old path before `ClassLoader` reads it, causing a time-of-check/time-of-use flaw.
6. **Malicious code still signed by a trusted key:** keys can be stolen, and vendors can make mistakes or intentionally ship dangerous code. A signature does not restrict files, network, CPU, threads, or native libraries when the plugin runs.

Key takeaway: **never use class initialization, constructors, or `ServiceLoader` provider instances to verify the trustworthiness of an unverified JAR**. Those steps can already execute code. Always validate the artifact as raw bytes first, without executing anything.

## 3. Integrity: Comparing SHA-256 Against a Trusted Reference Source

SHA-256 maps bytes into a 256-bit digest. To check a downloaded plugin, the host computes the digest of the **exact file bytes** and compares it against a digest trusted by the system. If the file differs, the digest will differ barring cryptographic collisions, which are astronomically unlikely for SHA-256.

### 3.1. A Checksum from the Same Source Is Insufficient Proof

Suppose an untrusted endpoint returns both at once:

~~~text
analytics.jar
analytics.jar.sha256
~~~

If the endpoint is compromised, an adversary can replace both the JAR and `.sha256`. Computing SHA-256 will still show a "match", yet **there is no independent trust anchor**. Solutions include: digests obtained from a verified signed release manifest, digests approved by an administrator, or a datastore protected by a separate change-control process.

A hash supplied alongside an artifact by the sender is still useful for detecting transmission errors, but it is **not proof of publisher identity**.

### 3.2. Hash the Exact Bytes, Not the Filename

For SHA-256 over a JAR:

- Use the original raw bytes of the artifact. Do not normalize newlines, unpack and repack, alter ZIP timestamps, or reorder entries before computing the whole-file hash.
- The hash must bind to the exact plugin ID/version/artifact the host intends to use; do not accept a valid digest belonging to **another release**.
- Java provides `MessageDigest.getInstance("SHA-256")` and `MessageDigest.isEqual` for byte-level digest comparison.
- For large files, read as a stream, enforce download size limits, and move only verified data into an immutable artifact store.
- ZIP CRC-32 helps detect accidental data corruption, but **CRC-32 is not designed to resist an active adversary**.
- On mismatch, fail closed; never automatically overwrite the expected digest with the newly observed digest.

Illustrative snippet placed inside a method where `jarPath` and `trustedDigest` (`byte[]`) already exist:

~~~java
byte[] content = java.nio.file.Files.readAllBytes(jarPath);
byte[] currentDigest = java.security.MessageDigest
        .getInstance("SHA-256").digest(content);
boolean intact = java.security.MessageDigest.isEqual(
        trustedDigest, currentDigest);
~~~

This is **not a standalone Java class**; it illustrates the check. `Files.readAllBytes` is only reasonable for size-bounded artifacts. In production, you can hash sequentially from a stream to avoid loading the entire JAR onto the heap.

### 3.3. SHA-256 Contains No Signer Information

SHA-256 only produces a data fingerprint; it contains no certificates, private keys, or identity. Anyone who possesses a file can compute its SHA-256. When a digest is protected by a trusted publisher's signature, it is the **signature on the manifest** that binds the digest to the publishing source, not the hash function itself.

Do not treat two downloads having the same checksum as proof that there is no malware. If both downloads received the exact same compromised build already planted in the repository, the values will still match.

## 4. Digital Signature: Verifying the Signing Operation, Not Automatically Granting Signer Authority

When signing digitally, the signer uses a **private key** to create a signature over a byte sequence; the verifier uses a **public key** to check it.

~~~text
Publisher:
  bytes(JAR) + private key → sign → signature

Host:
  bytes(JAR) + signature + public key → verify → true / false
~~~

For Ed25519 (available in JDK 17's cryptographic APIs), Java uses `KeyPairGenerator.getInstance("Ed25519")` and `Signature.getInstance("Ed25519")`. If the JAR's bytes change after signing while keeping the old signature, verification must reject it.

**Limitation of a `true` result:** `verify` proves the signature is valid under the public key used for checking, but **it does not by itself prove that the public key belongs to a vendor authorized by the host**. If the host accepts both the public key and the JAR from an untrusted request, an adversary can simply generate their own keypair, sign the file, and supply their own public key. `verify` will still return `true`.

To go a step further, the public key must be authenticated via:

- **Key pinning:** the host is pre-provisioned with the public key or fingerprint of an authorized signer from a trusted administrative configuration.
- **X.509/certificate validation:** checking the certificate chain up to an accepted trust anchor, validity period, intended usage, revocation, and matching identity.
- **Signed release metadata:** a signed manifest binding plugin ID, version, artifact digest, and signer identity.

Do not take a "trusted key" from unverified metadata inside **the very JAR being evaluated**. A trust anchor self-proposed by an adversary guarantees nothing.

### 4.1. What You Sign Is What You Protect

A signature only protects **the scope of data that was signed**. If a signature covers `plugin.jar` while a `plugin-permissions.json` file alongside it is unsigned, the host cannot infer that the permission metadata has not been modified.

Two common models:

1. **Detached whole-artifact signature:** a separate signature covering every byte of the entire JAR; altering any byte anywhere in the archive causes the whole-file signature check to fail.
2. **Signed release manifest:** a signature covering a manifest containing digests of the JAR, dependencies, critical configs, and metadata. The host verifies the manifest and then verifies the digest of each artifact in turn.

Java's **built-in JAR signing mechanism with `jarsigner`** differs from those two models in details involving the manifest, signature files, and signed entries. Do not confuse signing listed entries with signing the raw bytes of the ZIP container.

### 4.2. Key Possession Is Different from Identity and Safety

An unknown publisher can still create **a valid signature using their own key**. This does not "break" cryptography. Conversely, an attacker who steals a trusted publisher's private key can also create mathematically valid signatures. Therefore:

- Verification confirms cryptographic properties of the byte sequence and key.
- Publisher trust decides whether the key/cert belongs to the accepted list.
- Authorization decides which plugin IDs/capabilities that signer may publish.
- Security reviews, sandboxes, and monitoring address **code behavior** issues, which lie outside the signature itself.

## 5. Publisher Trust: From a Recognized Key to Publishing Authority

A host may have multiple vendors. A policy should be maintained separately from the artifact, for example:

~~~text
TrustedPublisherPolicy
  publisherId: vendor-alpha
  publicKeyFingerprint: value obtained from a trusted key-provisioning process
  permittedPluginIds: com.example.analytics, com.example.reports
  permittedCapabilities: read:catalog
  minimumAllowedVersion: version per policy
  revokedVersions: list of revoked versions
  enabled: true
~~~

The block above is a **policy schema**, not a runnable configuration file. In a real implementation, keys/fingerprints and permission lists must come from an authenticated management system, never self-declared by the plugin itself.

The verification chain may look like:

~~~text
received JAR + signature
          |
          v
cryptographic signature valid?
          |
          v
signing key/certificate recognized?
          |
          v
publisher authorized for requested plugin ID/version?
          |
          v
all release artifacts and capabilities approved?
          |
          v
may proceed to controlled loading
~~~

If any mandatory step fails, class loading must not proceed. With certificate chains, "a CA signed this certificate" only assists in authenticating an entity under a trust policy; it does **not** automatically grant authority to publish every plugin. An entity holding a valid code-signing certificate may still not be a partner of the system.

### 5.1. Decision Map

| Scenario | Hash against trusted source | Signature | Publisher policy | Decision |
| --- | --- | --- | --- | --- |
| Exact approved release | Match | Valid | Allowed | Allow proceeding to loading step |
| JAR modified after signing | Mismatch | Invalid against old signature | No need to evaluate further | Reject |
| JAR signed by unknown key | Not necessarily an approved digest | Valid under unknown key | Not allowed | Reject |
| Vendor A signs B's plugin ID | May match metadata published by A | Valid for A | A is not authorized to publish B | Reject |
| Old vulnerable release, revoked | May match | May be valid | Release rejected | Reject |
| Valid release but plugin has a bug | Match | Valid | May be allowed | Runtime controls still required |

A good policy does not merely store a list of "keys with valid signatures", but also includes **scope and timing**: which publisher, which plugin IDs, which versions, which permissions, effective dates, and revocation status.

## 6. Runnable Java 17 Example: SHA-256, Ed25519, and Pinned Signer

This example creates **two real byte-level JARs** using `JarOutputStream`, generates **two Ed25519 keypairs**, signs, and verifies:

- **original:** an archive containing `plugin-v1`, signed with the trusted private key.
- **modified:** an archive containing `plugin-v2`, differing in bytes from the verified version.
- **unknown:** an unaccepted party signs the `modified` archive with its own private key. Its signature is still valid when verified with its own public key.
- **approved:** a simulated host check requiring **the signer's key to match the pinned public key** and the signature to be valid over the JAR bytes.

The example **does not sign the JAR in `jarsigner` format**, instead using a detached Ed25519 signature covering all bytes of the JAR. The goal is to clarify the three types of checks, not to implement X.509/PKIX or JAR entry-signing logic.

**Important:** the example generates the trusted keypair in memory so it can run standalone, so it only simulates key pinning. In a real product, the signer private key stays on the publisher's side; the host receives the trusted public key beforehand through independent provisioning and never creates a "trusted" key from an unknown artifact.

### 6.1. File `PluginTrustDemo.java`

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;

public final class PluginTrustDemo {
    private static byte[] jarBytes(String content) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (JarOutputStream jar = new JarOutputStream(buffer)) {
            JarEntry entry = new JarEntry("plugin.txt");
            entry.setTime(0L);
            jar.putNextEntry(entry);
            jar.write(content.getBytes(StandardCharsets.UTF_8));
            jar.closeEntry();
        }
        return buffer.toByteArray();
    }

    private static byte[] digest(byte[] content) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(content);
    }

    private static byte[] sign(byte[] content, PrivateKey key)
            throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(key);
        signer.update(content);
        return signer.sign();
    }

    private static boolean verify(byte[] content, byte[] signature,
                                  PublicKey key) throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        verifier.update(content);
        return verifier.verify(signature);
    }

    private static boolean approved(byte[] content, byte[] signature,
                                    PublicKey claimedKey,
                                    PublicKey pinnedKey) throws Exception {
        boolean knownKey = MessageDigest.isEqual(
                claimedKey.getEncoded(), pinnedKey.getEncoded());
        return knownKey && verify(content, signature, pinnedKey);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair trusted = generator.generateKeyPair();
        KeyPair unknown = generator.generateKeyPair();

        byte[] original = jarBytes("plugin-v1");
        byte[] modified = jarBytes("plugin-v2");
        byte[] approvedDigest = digest(original);
        byte[] trustedSignature = sign(original, trusted.getPrivate());
        byte[] unknownSignature = sign(modified, unknown.getPrivate());

        System.out.println("hash.original=" +
                MessageDigest.isEqual(approvedDigest, digest(original)));
        System.out.println("hash.modified=" +
                MessageDigest.isEqual(approvedDigest, digest(modified)));
        System.out.println("signature.original=" +
                verify(original, trustedSignature, trusted.getPublic()));
        System.out.println("signature.modified=" +
                verify(modified, trustedSignature, trusted.getPublic()));
        System.out.println("signature.unknownOwnKey=" +
                verify(modified, unknownSignature, unknown.getPublic()));
        System.out.println("publisher.unknownTrusted=" +
                MessageDigest.isEqual(unknown.getPublic().getEncoded(),
                        trusted.getPublic().getEncoded()));
        System.out.println("policy.original=" +
                approved(original, trustedSignature,
                        trusted.getPublic(), trusted.getPublic()));
        System.out.println("policy.modified=" +
                approved(modified, trustedSignature,
                        trusted.getPublic(), trusted.getPublic()));
        System.out.println("policy.unknown=" +
                approved(modified, unknownSignature,
                        unknown.getPublic(), trusted.getPublic()));
    }
}
~~~

The code uses `KeyPairGenerator`, `MessageDigest`, and `Signature` from JDK 17's `java.base`, requiring no external dependencies. `JarOutputStream` creates a real archive; the `plugin.txt` entry holds simulated data, so no unverified code is loaded.

### 6.2. Compiling, Running, and Exact Stdout

In the directory containing **PluginTrustDemo.java**, using JDK 17 or newer:

~~~powershell
javac --release 17 -encoding UTF-8 PluginTrustDemo.java
java PluginTrustDemo
~~~

Equivalent commands apply on Linux/macOS when `javac`/`java` are available. The program does not write private keys to disk.

**Stdout verified by actual compilation and execution:**

~~~text
hash.original=true
hash.modified=false
signature.original=true
signature.modified=false
signature.unknownOwnKey=true
publisher.unknownTrusted=false
policy.original=true
policy.modified=false
policy.unknown=false
~~~

### 6.3. Analyzing Each Result

- **hash.original=true:** the current digest of `original` matches the digest precomputed from `original`.
- **hash.modified=false:** `modified` contains `plugin-v2` and no longer matches `plugin-v1`'s digest.
- **signature.original=true:** the `original` bytes match the signature created by the trusted private key.
- **signature.modified=false:** the `modified` bytes do not correspond to the original signature.
- **signature.unknownOwnKey=true:** a stranger can easily create a valid signature using their own private key. **This is not forging a trusted signature**.
- **publisher.unknownTrusted=false:** the `unknown` public key is not the host's pinned key.
- **policy.original=true:** the pinned key matches the signer key and the signature is valid.
- **policy.modified=false:** the original signature is no longer valid after the JAR bytes changed.
- **policy.unknown=false:** `unknown`'s signature is valid for the `unknown` key, but fails the trust step.

The code uses only two example-generated keys and a simulated pin. In a real system, `approved` must also bind the exact **plugin ID**, **publisher identity**, **release policy**, **dependency set**, certificate validity/revocation if using X.509, and the loaded artifact snapshot. Do not treat this method as a production-ready verifier.

## 7. Detached Signature vs. JAR Signing with `jarsigner`

A **detached signature** as in section 6 signs an explicit byte sequence, such as the entire `plugin.jar` file. Changing any byte within the signed scope causes the signature to stop matching.

By contrast, Java's **signed JAR** under the JAR File Specification uses a structure inside `META-INF`:

~~~text
META-INF/MANIFEST.MF
META-INF/<SIGNER>.SF
META-INF/<SIGNER>.RSA or corresponding signature block
~~~

Here `<SIGNER>` is merely a **placeholder for the tool-generated filename**, not a real name. Depending on the algorithm/tooling, the signature block may use other extensions, such as `.DSA` or `.EC`.

Under the JAR signing model:

1. `MANIFEST.MF` holds digests of the relevant JAR entries.
2. The `.SF` file holds digests of the manifest or relevant manifest sections.
3. The signature block confirms the cryptographic signature of the `.SF` file.
4. The verifier uses this chain to check whether the **signed entries** have been altered.

This verifies **signed entries and metadata**, rather than simply signing every ZIP byte via a single `Signature.update(allBytes)` call. If a new entry is added after signing and is not included in the entry set covered by the original signature, the signature on the older entries may still verify successfully. Therefore, a clear **unsigned entry** policy is required.

### 7.1. `jarsigner` Command for Verification

Once you have a genuinely signed JAR, run:

~~~powershell
jarsigner -verify -verbose -certs -strict plugin.jar
~~~

- **-verify** checks the signature.
- **-verbose** lists additional entry status details.
- **-certs** displays certificate information.
- **-strict** enforces strict handling of severe warnings, which can yield a non-zero exit code when the chain cannot be validated, a certificate is self-signed, unsigned entries are present, or an algorithm is rejected.

There is no fixed stdout for this command: the output depends on the JAR, signer, truststore, certificate chain, timestamp, and running JDK. **Merely seeing "jar verified" or seeing a `.SF` file does not mean the publisher has been accepted by the host.**

`jarsigner` can verify a signature using a certificate carried inside the JAR itself. If that certificate is **self-signed** or its chain is not trusted under policy, cryptographic validity alone does not prove a trusted source. Even when using a specific keystore/truststore, you must still confirm that the alias/signer matches **an authorized publisher**.

### 7.2. Verification via the Java `JarFile` API

`JarFile` has a verification mode for signed JARs. However, **opening a JAR or listing entries does not prove that all entry contents were verified**. Digest verification typically occurs when entry data is actually read; to evaluate signer metadata for an entry, you must ensure the entry's data has been fully consumed and checked.

Before using an entry's signer to make a decision, the host must distinguish:

- An entry has a `CodeSigner`/certificate matching policy.
- An entry has no signer, even though other entries in the JAR are signed.
- An entry has a valid signer, but that signer is not authorized by the host.
- An entry is corrupted or fails digest verification while being read.
- Dependencies or config files **outside the JAR** are not covered by the JAR's signature.

Reading and verifying entries does not replace **PKIX trust** checks, allowlists, or the host's own plugin authorization. If the system requires all classes/resources to be signed, you must verify **coverage over every entry actually used**, not merely the presence of signature metadata.

### 7.3. Do Not Equate JAR Signing with Unconditional JAR Trust

A properly signed JAR can still be signed by any individual using their own keypair. A JAR with a recognized signer can still be a release containing malware, backdoors, or bugs. A newly added unsigned entry does not become trustworthy just because the JAR retains the signature block of older entries.

The right approach is to verify the **signature** first, authenticate the **signer/trust anchor**, check **signing coverage and release policy**, and only then decide whether to grant permission to load.

## 8. X.509, PKIX, and Code-Signing Certificates: Steps Beyond the Signature

If the publisher uses X.509 certificates, many checks beyond `Signature.verify` are required:

| Check | Goal | If omitted |
| --- | --- | --- |
| Data signature | The signature is genuinely valid over the protected data | Altered files may be accepted |
| Chain validation | The certificate chains up to an allowed trust anchor | Self-signed certificates from strangers are trusted |
| Validity | The certificate is valid under the time policy | Expired or not-yet-valid certificates are accepted |
| Revocation | The certificate/key has not been revoked under policy | Disabled/compromised keys are trusted |
| KeyUsage / ExtendedKeyUsage | The certificate suits code signing if required by policy | Wrong type of certificate is used |
| Identity binding | The verified identity corresponds to the right vendor | Self-declared Subject/CN spoofing |
| Publisher authorization | The vendor is authorized to release that exact plugin ID/capability | One valid cert can be used to sign any plugin |

**The Subject/CN name on a certificate is not enough** to authenticate a publisher. Verifying the signature with the public key extracted from the certificate is also insufficient: you must validate the certificate chain/trust anchor and identity policy.

Revocation checking may require CRL, OCSP, or a dedicated key-status source; not every verify call performs this automatically. When revocation information cannot be fetched, the application must intentionally define fail-closed vs. fail-open behavior according to security requirements.

A **trusted timestamp** can help evaluate signing time relative to a certificate's validity window, but a timestamp does not legitimize an invalid signature or an unauthorized publisher. The timestamp authority and related information must also be authenticated.

A **truststore** is not equivalent to a plugin publisher list. Even a certificate with a trusted PKIX chain is not necessarily authorized to release `com.example.analytics`. The host must still map the signer identity to the **plugin ID**, version, and release rules.

## 9. Protecting Metadata and Dependencies Outside the JAR

A plugin package may have a structure like:

~~~text
release/
  manifest.json
  manifest.sig
  plugin.jar
  lib/dependency-a.jar
  lib/dependency-b.jar
  config/plugin.properties
~~~

Signing only `plugin.jar` while the host automatically downloads dependencies from an uncontrolled URL leaves the boundary exposed. A release can bind:

- Plugin ID and version.
- Publisher identity and signing key ID/chain.
- SHA-256 of `plugin.jar`.
- SHA-256 of each dependency JAR.
- SHA-256 of resources/configs that affect how the plugin runs.
- Capability / minimum version / revocation policies.
- Timestamps or build/provenance metadata if needed.

After verifying the manifest signature from an authorized publisher, the host computes the SHA-256 of **each file** and compares it. Any file that can alter behavior during loading or activation must be covered by an appropriate policy.

An illustrative manifest structure, **not a real signed artifact**:

~~~json
{
  "pluginId": "com.example.analytics",
  "version": "2.4.1",
  "publisherId": "vendor-alpha",
  "artifacts": [
    {"path": "plugin.jar", "digestAlgorithm": "SHA-256"},
    {"path": "lib/dependency-a.jar", "digestAlgorithm": "SHA-256"}
  ]
}
~~~

There are no real digest values here, so the JSON only shows the required metadata fields; **do not use it for production verification**. A real manifest must contain valid digests, be signed over a clearly specified byte representation (ensuring consistent canonicalization), and the host must verify both the manifest signature and every individual artifact.

Beyond signatures/digests, extracting ZIP/JAR archives must guard against path traversal, symlinks, duplicate entry names, and size limits. A valid signature does not automatically make extraction safe.

## 10. Verification Order Before `ClassLoader` and `ServiceLoader`

Recommended sequence for a plugin manager:

1. **Download to staging:** do not load classes yet; block oversized files, invalid names/paths, and mixed requests.
2. **Fetch release record from a trusted source:** determine the expected plugin ID/version and publisher identity under host policy.
3. **Check SHA-256:** compare the exact bytes of the artifact against the protected digest; stop on failure.
4. **Verify signature:** use the right algorithm, exact data, and checked signer key.
5. **Check signer trust:** pin, certificate chain, and revocation/timestamp/validity per environment.
6. **Check authorization:** is the publisher allowed to sign this exact plugin ID/version/capability? Are any artifacts/dependencies revoked?
7. **Pin the verified bytes:** place the snapshot into an immutable area or content-addressed path.
8. **Only then create loaders/module layers and providers:** scan SPI, invoke constructors, prepare/activate according to the plugin lifecycle.
9. **Monitor at runtime:** audit, enforce permission limits, and provide a mechanism to disable the plugin on security advisories.

If any mandatory condition cannot be verified, **fail closed** instead of "trying to load it to see if it runs".

### 10.1. Avoiding Time-of-Check/Time-of-Use (TOCTOU)

A dangerous sequence:

~~~text
verify /tmp/plugin.jar
         |
         | another process overwrites the file
         v
new URLClassLoader(/tmp/plugin.jar)
         |
         v
execute altered plugin
~~~

Even if the initial verification was flawless, the system may execute **a different file** if the path is altered afterward. Mitigations:

- Staging directory with strict access permissions so unauthorized actors cannot overwrite files.
- Snapshot the verified bytes and publish them as an immutable artifact.
- Use content-addressed storage or digest-named files protected against modification.
- Create the loader from **the exact verified artifact** and check dependencies separately.
- Do not automatically reuse a path that could be modified between checking and loading.

Never treat an **identical filename** as proof that the file still contains the verified bytes.

### 10.2. `ClassLoader` Is Not a Sandbox and Can Trigger Code on Load

Separating loaders isolates class/dependency namespaces; it does not restrict file/network privileges or code behavior. Constructors, class static initialization, provider factories, or `ServiceLoader.Provider.get()` can execute code. Therefore, never rely on **self-reported claims from an untrusted plugin instance** to decide whether that plugin is trusted.

Once an artifact has been accepted, the host must still manage the plugin's permissions, resources, timeouts, stop/close lifecycle, and reference cleanup during reload.

## 11. HTTPS and Provenance Are Supporting Layers, Not Replacements for the Three Checks

HTTPS protects the connection to an authenticated endpoint, but does not address cases where the artifact repository itself is compromised, a file is uploaded by mistake, or repository admin privileges are abused. Release signatures enable authenticating the publishing origin independently of the transport channel.

An **SBOM** lists declared components; it does not authenticate publisher identity or prove that components have no vulnerabilities. A signed build provenance/attestation can clarify the artifact production pipeline, yet the provenance signature itself must also be verified with the proper identity/trust and bound to the exact deployed artifact bytes.

Do not equate these pieces of evidence with an "absolutely safe artifact". They support supply-chain control, reviews, and incident investigation, while runtime capability policies remain necessary.

## 12. Key Management, Revocation, and Anti-Downgrade

### 12.1. Key Rotation

A solid pinning design must include a key-rotation procedure:

1. Generate the new key in a trusted environment and protect the private key (KMS/HSM or equivalent process).
2. Publish the new public key via an authenticated administrative channel; never trust a key arriving inside an unverified JAR.
3. Define validity windows and release scopes signed with the old and new keys.
4. Audit truststore/policy changes and avoid silent pin updates.
5. Revoke old keys upon expiration or incident; do not accept old signatures for releases forbidden by policy.

### 12.2. Valid Signatures Do Not Detect Stolen Private Keys

If an attacker obtains a vendor's real private key, they can produce valid signatures matching **the pinned public key itself**. Mathematical verification cannot distinguish the legitimate signer from someone wielding a stolen key. In an incident, you need independent revocation/release-approval policies, signing-system monitoring, release-permission controls, and plugin freeze/revocation workflows.

A signature with a trusted timestamp helps evaluate signing time against policy, but does not eliminate the need for incident response.

### 12.3. Rollback and Versioning

An older build may still be properly signed while containing vulnerabilities. The system needs a minimum accepted version, a list of revoked releases, or explicit approval for rollbacks. Do not use plain string comparisons to determine version ordering if semantic versions are unnormalized; use a consistent version parser/policy.

If an artifact is revoked after already being loaded, the system also needs to handle **running instances**: stop routing, shut down the plugin, close resources, release the loader where possible, and update audit logs. Merely blocking future loads may not be enough.

## 13. Common Misconceptions

| Misconception | Why it is wrong | How to fix |
| --- | --- | --- |
| "SHA-256 matches the `.sha256` at the same URL, so it must be safe." | An attacker can replace both | Protect expected hashes with a signed manifest or trusted channel |
| "A valid signature means the publisher is trusted." | Anyone can sign with their own key | Pin keys or validate certificate chains + policy |
| "Subject/CN matches the vendor name, so it is valid." | Names inside a cert do not prove the chain/identity | PKIX validation, trust anchor checks, and identity binding |
| "`jarsigner` reporting verified is enough to load." | It does not know which plugin IDs the publisher is authorized for | Check signer trust and release authorization |
| "Having `META-INF/*.SF` means every entry is signed." | The signature file may be malformed; some entries may be unsigned | Verify signatures and signer coverage |
| "Any signer with a CA-trusted cert can publish plugins." | Trusting a CA differs from publishing authorization in the system | Map identity → plugin ID/version/capability |
| "An unexpired certificate cannot be revoked." | Expiration and revocation are separate states | Check revocation per policy |
| "A separate `ClassLoader` makes untrusted code safe." | The plugin can still use the host process's privileges | Least privilege, process isolation when needed |
| "Verify first and reload the same path later uses the same bytes." | The file can change after verification | Immutable snapshots or immutable paths |
| "Signed artifacts cannot contain vulnerabilities." | Signatures do not analyze code logic | Reviews, scanning, monitoring, and revocation |

## 14. Test Suite for a Plugin Verifier

Both passing and failing cases must be tested:

| Test | Expectation |
| --- | --- |
| Valid artifact, approved signer, valid version | ACCEPT after all checks |
| Modify bytes inside JAR, keep old signature | HASH_MISMATCH or SIGNATURE_INVALID |
| Replace signature with random bytes | SIGNATURE_INVALID |
| Sign another JAR with a new keypair | Signature may be valid for the new key, but REJECT signer |
| Same vendor mistakenly signs an unauthorized plugin ID | PUBLISHER_NOT_AUTHORIZED |
| Unpinned self-signed certificate | REJECT signer |
| Certificate revoked/expired per policy | REJECT according to validity rules |
| New unsigned entry added to a JAR with older signed entries | REJECT if policy requires full coverage |
| Dependency JAR bytes differ from signed release manifest | REJECT due to digest mismatch |
| Old release version that was withdrawn | REJECT even if old signature is still valid |
| File modified between verify and load | Do not load the new contents |
| Network error, read error, missing key, unknown trust info | FAIL CLOSED when mandatory conditions cannot be verified |
| Artifact has valid signature but requests excessive capabilities | Deny capabilities or loading per policy |

Useful audit details: plugin ID/version, expected signer identity, fingerprint, actual SHA-256, timestamp, per-layer check results, and final decision. Do not log private keys or verbatim sensitive plugin data.

## 15. Pre-Execution Plugin Acceptance Checklist

1. **Integrity:** does the current digest match the approved release from a trusted source?
2. **Signature:** was the signature verified over the exact bytes and scope of artifacts requiring protection?
3. **Signer identity:** is the key/certificate recognized via a pin or validated chain?
4. **Publisher authorization:** is that signer authorized to sign this exact plugin ID, version, and capabilities?
5. **Certificate policy:** do validity, revocation, key usage, timestamp, and algorithms pass?
6. **Release metadata:** are dependencies, configs, and executable resources covered by a signed manifest or equivalent mechanism?
7. **Anti-rollback:** is the release banned, revoked, or below the minimum version?
8. **TOCTOU:** does the loader use the exact verified bytes?
9. **Lifecycle:** are providers created/initialized, prepared, activated, and published for readiness only after acceptance?
10. **Runtime defense:** are resource/permission limits, monitoring, stopping, and plugin revocation in place when needed?

For unverified outcomes, use **UNKNOWN/NOT_CHECKED** status rather than defaulting to `true`. A function returning only `isSignatureValid` cannot represent the host's complete verdict.

## 16. Self-Check Questions

**Is a file having the same SHA-256 hash as a checksum downloaded from the same untrusted endpoint sufficient?** No. The expected digest must be protected by an independent trusted source.

**Why can an attacker's signature return `true`?** Because they sign with their own private key and supply the corresponding public key. Verification is a cryptographic check; publisher trust requires another step.

**What must be verified after knowing a signer's cert has a trusted chain?** You must check exact identity, authority to publish the plugin ID/capabilities, revocation/version status, and the scope of signed artifacts.

**What if a signed JAR contains a newly added unsigned entry?** Signatures of older entries may still be valid; the host must enforce a policy for unsigned entries rather than assuming the entire archive is authenticated.

**Why must verification happen before `ServiceLoader.Provider.get()`?** Because that call can instantiate the provider and execute its constructor/static initializers.

**Does a valid signature prove a plugin cannot access the network or host files?** No. That belongs to runtime policy and isolation, not digital signatures.

### Official References

- Oracle Java SE 17, **MessageDigest**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- Oracle Java SE 17, **Signature**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html
- Oracle Java SE 17, **KeyPairGenerator**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html
- Oracle Java SE 17, **JarFile** and verifying entries: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- Oracle, **JAR File Specification**: https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html
- Oracle, **jarsigner Command**, verify/strict/certificates: https://docs.oracle.com/en/java/javase/22/docs/specs/man/jarsigner.html
- Oracle Java SE 17, **CertPathValidator**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html
- Oracle Java SE 17, **PKIXParameters**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html

**Conclusion:** **Integrity** answers "are these the exact bytes of the accepted release?"; **digital signature** answers "does the signature match the signing key over the signed data?"; **publisher trust** answers "is that key/identity authorized by the host to publish this exact plugin?". All three must form a connected chain of trust **before the plugin is loaded or activated**. Even after acceptance, permissions and lifecycle controls remain necessary, because a signature authenticates origin rather than guaranteeing code behavior.
