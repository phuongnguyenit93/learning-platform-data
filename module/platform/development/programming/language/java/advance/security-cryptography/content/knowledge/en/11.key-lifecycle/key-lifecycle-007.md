# 11.7 Exportable Keys vs. Provider-Bound Keys

## 1. Why Do Two `Key` Objects Share the Same Interface Yet Have Different Control Levels?

In the Java Cryptography Architecture/Extension (JCA/JCE), the interfaces `java.security.Key`, `SecretKey`, `PublicKey`, and `PrivateKey` only describe a key and the operations executable through a provider. They **do not** guarantee whether the key material resides in the JVM, a file, the OS, a hardware token/HSM, or a KMS service.

Two concepts must be distinguished:

- **Exportable key:** has a byte representation of the secret/private key permitted to be extracted, usually via `key.getEncoded()`; the Java process can hold, copy, store, or re-import it using appropriate APIs. Every copy widens the exposure surface: heap, core dumps, debuggers, logs, files, backups, network, and downstream services.
- **Provider-only key (provider-bound/opaque):** Java holds a **handle** referencing a key inside a token/HSM/specialized keystore or adapter. The backend owns the key material, can forbid retrieving raw bytes, yet still permits calling `sign`, `decrypt`, `encrypt`, `MAC`, `derive`, or `wrap` per policy. The goal is to **use the key without handing key material to the application**.

```text
Java Application
   |
   +---- exportable SecretKey/PrivateKey
   |          |
   |      getEncoded() -> byte[]
   |          |
   |      can be imported/copied/stored if permitted
   |          |
   |      Cipher/Signature on a compatible provider
   |
   +---- opaque provider key handle
              |
          getEncoded() -> typically null
              |
          Cipher/Signature/KeyAgreement
              |
          provider -> token/HSM/KMS adapter
                         |
                    permitted operation
                         |
                    returns result, never raw key
```

**Important:** `getEncoded()==null` only proves that the Java API did not provide an encoding through that call. It **is not sufficient proof that a key is hardware non-extractable** or impossible to extract via every other API; nor does it **make a mocked key usable with a provider**. Real assurance depends on key attributes, token policies, IAM, import/generation mechanisms, firmware, and security audits.

## 2. Contract of `Key.getAlgorithm`, `getFormat`, and `getEncoded`

| API | What Does It Mean? | What Does It Not Mean? |
| --- | --- | --- |
| `getAlgorithm()` | Algorithm name such as `AES`, `RSA`, `EC` | Does not state where the key was created, whether usage is authorized, or whether it is exportable |
| `getFormat()` | Encoding format if available: `RAW`, `X.509`, `PKCS#8`, or `null` | Not a data protection mechanism; `null` does not verify HSM custody |
| `getEncoded()` | Encoded bytes if the provider supports it, or `null` | Does not prove owner identity; does not authorize wrapping/export or ensure all copies are wiped |

In Java 17+ with standard software providers:

- `KeyGenerator.getInstance("AES")` normally generates a `SecretKey` with `getFormat() == "RAW"`; `getEncoded()` returns 16, 24, or 32 bytes for AES-128/192/256.
- An RSA public key from `KeyPairGenerator` normally has `getFormat()=="X.509"` and DER `SubjectPublicKeyInfo` bytes. It can be reconstructed via `X509EncodedKeySpec` and `KeyFactory("RSA")`.
- A software RSA private key normally has `getFormat()=="PKCS#8"` and DER `PrivateKeyInfo`. It can be reconstructed via `PKCS8EncodedKeySpec` and `KeyFactory("RSA")` when permitted.
- A hardware key may allow exporting the **public key** while forbidding export of the matching **private key**. The public key still requires source/identity verification before protocol use; it itself is not a secret.

### Key Export vs. Key Usage

A key can be exportable yet restricted by policy to signing only; conversely, an opaque key may sign and decrypt inside the backend without ever returning raw material. The permissions `sign`, `verify`, `encrypt`, `decrypt`, `derive`, `wrap`, and `unwrap` are **separate** rights/capabilities. A token may hold a key allowing `CKA_SIGN` without `CKA_DECRYPT`; the application must never infer from the algorithm name that every operation is permitted.

`getEncoded()` may return `null` for keys that do not support encoding. Never handle `null` by substituting `new byte[0]`, hashing a key ID into a raw key, or trying to extract a private key from serialized `toString()` or reflective fields. A handle is not raw key material.

## 3. When Key Export Is Permitted, Understand the Formats Properly

| Type | Common `getFormat()` | Returned Bytes | Reconstruction API |
| --- | --- | --- | --- |
| Software AES/HMAC secret key | `RAW` | Secret bytes with proper entropy | `SecretKeySpec(raw,"AES")` or matching algorithm name |
| RSA public | `X.509` | DER SubjectPublicKeyInfo | `KeyFactory("RSA").generatePublic(new X509EncodedKeySpec(der))` |
| RSA private | `PKCS#8` | DER PrivateKeyInfo | `KeyFactory("RSA").generatePrivate(new PKCS8EncodedKeySpec(der))` |
| Software EC public/private | `X.509` / `PKCS#8` | DER containing algorithm/curve | `KeyFactory("EC")` with matching spec type |
| Non-exportable HSM key | may be `null` | `getEncoded()==null` | Use key handle via provider; never re-import from `byte[]` |

Having the right AES byte length is only a syntactic requirement: 16/24/32 bytes **does not guarantee entropy**. `SecretKeySpec` creates no randomness, does not check source trust, and **does not turn a plain byte array into an HSM-resident key**. Use `KeyGenerator` and `SecureRandom` for new keys, or securely provisioned raw bytes.

Do not confuse **PEM** (Base64 text armor) with **DER** (binary ASN.1 encoding): `PKCS8EncodedKeySpec` takes DER, not the ASCII bytes of `-----BEGIN PRIVATE KEY-----`. Moreover, `BEGIN PRIVATE KEY` is **unencrypted** PKCS#8; `BEGIN ENCRYPTED PRIVATE KEY` is a password/algorithm-protected container requiring `EncryptedPrivateKeyInfo` processing first. Base64/hex is only encoding; it does not make a private key more secret.

### Risks of Exporting

Calling `getEncoded()` on a private/secret key **creates another copy of sensitive material**. Avoid doing it merely for fingerprinting, debugging, or passing objects across modules. If exporting is strictly needed for backup or migration: restrict authorized principals, establish an encrypted channel, apply least privilege, audit, wrap the key, and purge copies per policy.

`Arrays.fill(bytes,(byte)0)` reduces the lifetime of the application's byte array, yet does not wipe key copies inside `SecretKeySpec`, the provider, `Cipher`, the JVM, or prior memory dumps. Converting a private key into a `String` is even harder to erase because strings are immutable. Likewise, `getEncoded()==null` does not guarantee zero sensitive material inside JVM internals.

## 4. Java 17+ Program: Exporting AES/RSA and a Simulated Opaque Key

Save as **`ExportabilityDemo.java`**. This complete program:

1. Generates AES-256 via `KeyGenerator` and obtains the software key's raw encoding.
2. Constructs `SecretKeySpec` from those bytes, encrypts via AES-GCM with the original key, and decrypts with the re-imported key.
3. Clears the array returned by `getEncoded()` and confirms the original key **still persists**.
4. Defines a mock `SecretKey` without an encoding (returning `null`); the software provider rejects it. This is **not a valid HSM mock**, but proof that a single API method return value is insufficient.
5. Exports/imports an RSA `PKCS#8` private key and `X.509` public key, signs a message, and verifies the signature.

```java
import java.nio.charset.StandardCharsets;
import java.security.InvalidKeyException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class ExportabilityDemo {
    private static final class OpaqueLookingKey implements SecretKey {
        public String getAlgorithm() { return "AES"; }
        public String getFormat() { return null; }
        public byte[] getEncoded() { return null; }
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        KeyGenerator kg = KeyGenerator.getInstance("AES");
        kg.init(256, random);
        SecretKey aes = kg.generateKey();

        byte[] exported = aes.getEncoded();
        if (exported == null) {
            throw new IllegalStateException("This demo requires exportable AES");
        }
        try {
            System.out.println("aesFormat=" + aes.getFormat());
            System.out.println("aesRawBytes=" + exported.length);
            SecretKey imported = new SecretKeySpec(exported, "AES");

            byte[] nonce = new byte[12];
            random.nextBytes(nonce);
            byte[] message = "key lifecycle".getBytes(StandardCharsets.UTF_8);
            Cipher encryption = Cipher.getInstance("AES/GCM/NoPadding");
            encryption.init(Cipher.ENCRYPT_MODE, aes,
                    new GCMParameterSpec(128, nonce));
            byte[] ciphertext = encryption.doFinal(message);
            Cipher decryption = Cipher.getInstance("AES/GCM/NoPadding");
            decryption.init(Cipher.DECRYPT_MODE, imported,
                    new GCMParameterSpec(128, nonce));
            System.out.println("aesRoundTrip=" +
                    Arrays.equals(message, decryption.doFinal(ciphertext)));

            Arrays.fill(exported, (byte) 0);
            byte[] checkCopy = aes.getEncoded();
            try {
                System.out.println("clearingCopyDoesNotDestroyKey="
                        + !MessageDigest.isEqual(exported, checkCopy));
            } finally {
                Arrays.fill(checkCopy, (byte) 0);
            }

            OpaqueLookingKey fake = new OpaqueLookingKey();
            System.out.println("mockEncodedNull=" + (fake.getEncoded() == null));
            try {
                Cipher unsupported = Cipher.getInstance("AES/GCM/NoPadding");
                unsupported.init(Cipher.ENCRYPT_MODE, fake,
                        new GCMParameterSpec(128, nonce));
                System.out.println("mockAccepted=false");
            } catch (InvalidKeyException expected) {
                System.out.println("mockRejectedByProvider=true");
            }
        } finally {
            Arrays.fill(exported, (byte) 0);
        }

        KeyPairGenerator rsa = KeyPairGenerator.getInstance("RSA");
        rsa.initialize(2048, random);
        KeyPair pair = rsa.generateKeyPair();
        byte[] publicDer = pair.getPublic().getEncoded();
        byte[] privateDer = pair.getPrivate().getEncoded();
        if (publicDer == null || privateDer == null) {
            throw new IllegalStateException("RSA example needs exportable keys");
        }
        try {
            System.out.println("rsaPublicFormat=" + pair.getPublic().getFormat());
            System.out.println("rsaPrivateFormat=" + pair.getPrivate().getFormat());
            KeyFactory factory = KeyFactory.getInstance("RSA");
            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(factory.generatePrivate(
                    new PKCS8EncodedKeySpec(privateDer)));
            byte[] message = "check".getBytes(StandardCharsets.UTF_8);
            signer.update(message);
            byte[] signature = signer.sign();
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(factory.generatePublic(
                    new X509EncodedKeySpec(publicDer)));
            verifier.update(message);
            System.out.println("importedRsaSignatureValid="
                    + verifier.verify(signature));
        } finally {
            Arrays.fill(publicDer, (byte) 0);
            Arrays.fill(privateDer, (byte) 0);
        }
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 ExportabilityDemo.java
java ExportabilityDemo
```

Output tested on JDK/SunJCE + RSA provider:

```text
aesFormat=RAW
aesRawBytes=32
aesRoundTrip=true
clearingCopyDoesNotDestroyKey=true
mockEncodedNull=true
mockRejectedByProvider=true
rsaPublicFormat=X.509
rsaPrivateFormat=PKCS#8
importedRsaSignatureValid=true
```

Explanation: `getEncoded()` hands out bytes the app can copy; wiping that copy does not destroy the generated `aes` key object. `OpaqueLookingKey` intentionally **has no managing provider**: `mockEncodedNull=true` does not mean the key is secure, and `mockRejectedByProvider=true` is the specific behavior of the AES provider in this test.

**GCM nonce:** the 12-byte `nonce` is used **once for encryption**, then reused **for decrypting that exact ciphertext**. For any **new encryption** under the same AES key, choose a **different** nonce; never repeat a key+nonce pair.

**RSA signing:** `KeyFactory` is instantiated for `RSA`. Use `X509EncodedKeySpec` for public keys and `PKCS8EncodedKeySpec` for private keys. Verified signatures show import worked properly, not that exporting private keys is a safe production policy.

## 5. Does Java `KeyStore` Make Keys Non-Exportable on Its Own?

**No.** `java.security.KeyStore` is an abstraction for storing and retrieving `PrivateKeyEntry`, `SecretKeyEntry`, and `TrustedCertificateEntry`. Whether raw export is allowed depends on the **store type/provider, key attributes, and where the key material actually lives**.

| Type | Characteristics | Can Keys Be Exported? |
| --- | --- | --- |
| Software `PKCS12` | Password-protected container/file; entries are retrieved once unlocked | Exportable; the demo below proves this |
| Legacy `JKS` | Software keystore primarily for private keys/certificates | Depends on entry/implementation; not an HSM |
| `PKCS11` on token/HSM | Provider invokes native PKCS#11; handles carry security attributes | Can be non-exportable per hardware policy |
| Android Keystore | Key handles backed by OS/hardware when available | Many private/secret keys forbid export; depends on API/device |
| Cloud KMS | Key IDs, IAM, audit, service APIs/RPC | Many keys never export raw bytes; SDKs may not provide JCA `Key` |

Password-protected PKCS12 protects **the stored file at rest**. Once unlocked, a software key can still allow `getEncoded()`; this is **different** from a key that never leaves an HSM.

### 5.1 Program: PKCS12 Can Hold an Exportable AES `SecretKeyEntry`

Save as **`Pkcs12ExportabilityDemo.java`**. This example runs in memory without creating a key file on disk. It stores an AES-256 key in PKCS12, reloads it with the matching password, and compares raw bytes. The sample passwords are for demo purposes only; never hard-code them in production code.

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class Pkcs12ExportabilityDemo {
    public static void main(String[] args) throws Exception {
        char[] storePassword = "demo-store-password".toCharArray();
        char[] entryPassword = "demo-entry-password".toCharArray();
        byte[] storedBytes = null;
        byte[] recoveredBytes = null;

        try {
            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(256, new SecureRandom());
            SecretKey generated = generator.generateKey();
            storedBytes = generated.getEncoded();
            if (storedBytes == null) {
                throw new IllegalStateException("Demo requires exportable key");
            }

            KeyStore store = KeyStore.getInstance("PKCS12");
            store.load(null, storePassword);
            KeyStore.ProtectionParameter protection =
                    new KeyStore.PasswordProtection(entryPassword);
            store.setEntry("session-key",
                    new KeyStore.SecretKeyEntry(generated), protection);
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            store.store(output, storePassword);

            KeyStore restored = KeyStore.getInstance("PKCS12");
            restored.load(new ByteArrayInputStream(output.toByteArray()),
                    storePassword);
            SecretKey restoredKey =
                    (SecretKey) restored.getKey("session-key", entryPassword);
            recoveredBytes = restoredKey.getEncoded();

            System.out.println("keystoreType=" + restored.getType());
            System.out.println("isSecretKeyEntry="
                    + restored.entryInstanceOf(
                            "session-key", KeyStore.SecretKeyEntry.class));
            System.out.println("recoveredExportable="
                    + (recoveredBytes != null));
            System.out.println("sameRawMaterial="
                    + (recoveredBytes != null
                    && MessageDigest.isEqual(storedBytes, recoveredBytes)));
        } finally {
            Arrays.fill(storePassword, '\0');
            Arrays.fill(entryPassword, '\0');
            if (storedBytes != null) Arrays.fill(storedBytes, (byte) 0);
            if (recoveredBytes != null) Arrays.fill(recoveredBytes, (byte) 0);
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 Pkcs12ExportabilityDemo.java
java Pkcs12ExportabilityDemo
```

```text
keystoreType=PKCS12
isSecretKeyEntry=true
recoveredExportable=true
sameRawMaterial=true
```

**Interpretation:** PKCS12 opens and extracts `SecretKeyEntry` successfully; `recoveredExportable=true` proves the keystore **does not automatically create a non-extractable constraint**. Another provider may differ in `SecretKeyEntry`/password support; always test in the target runtime. Even without writing a key file to disk, `ByteArrayOutputStream` and key objects hold sensitive copies on the heap, so the demo **does not** prove secure memory erasure.

## 6. True Opaque Keys Require a Provider That Understands Handles and Key Policies

An HSM key may be represented as a `PrivateKey` object whose `getEncoded() == null`. In that setup:

```text
Java KeyStore("PKCS11") --lookup alias--> HSM-backed PrivateKey handle
                                 |
Signature.initSign(handle) -------+-- token provider -- HSM sign()
                                            |
                                      signature bytes
```

Here **the private key material stays inside the HSM**, while Java receives the signature. Changing permitted operations requires device-supported mechanisms: a key marked only for `sign` does not automatically allow `decrypt` or `derive`. If the key lives in a cloud KMS, operations may be exposed via a REST/gRPC SDK rather than JCA `Signature` or `KeyStore`; never assume every KMS offers a JCA adapter.

**Provider matching:** `Signature.getInstance("SHA256withRSA",tokenProvider)` only works if that provider and key handle support that algorithm. `Cipher.getInstance("AES/GCM/NoPadding")` does not guarantee selecting the right provider for an opaque key; if it picks a software provider that cannot understand the handle, `Cipher.init` may throw `InvalidKeyException`. Choose the matching provider, transformation, and key usage explicitly.

### SunPKCS11 Integration Skeleton (Non-Standalone)

```java
// ILLUSTRATIVE ONLY: requires a real token/HSM, native PKCS#11 library, config,
// key alias, permissions, and PIN. Never hard-code the PIN.
java.security.Provider base =
        java.security.Security.getProvider("SunPKCS11");
if (base == null) {
    throw new IllegalStateException("SunPKCS11 unavailable");
}
java.security.Provider tokenProvider =
        base.configure("/secure/config/token-pkcs11.cfg");
java.security.KeyStore store =
        java.security.KeyStore.getInstance("PKCS11", tokenProvider);
store.load(null, pin);

java.security.Key key = store.getKey("signing-key", null);
if (!(key instanceof java.security.PrivateKey privateKey)) {
    throw new IllegalStateException("Signing key not found");
}
java.security.Signature signer =
        java.security.Signature.getInstance(
                "SHA256withRSA", tokenProvider);
signer.initSign(privateKey);
// signer.update(messageBytes); byte[] signature = signer.sign();
// Token/session cleanup and auditing per vendor policy.
```

`SunPKCS11` relies on the `jdk.crypto.cryptoki` module on JDKs that include it. Minimal runtimes may omit it; config files and the native PKCS#11 library/slot/token must be configured accurately. Token login/sessions and alias mapping vary across devices. This snippet **cannot create an opaque key** without a real HSM and key-generation policy; never use it to pretend an HSM is active merely because `getEncoded()==null`.

### Key Usage Can Still Be Dangerous

Non-extractable keys only restrict **extracting raw material**. If an attacker compromises a service permitted to call `sign`, they can produce unauthorized signatures; if permitted to call `decrypt`, they can obtain returned plaintext. **HSM/KMS does not replace authorization**. Restrict allowed payloads, key usage, IAM, rate limits, context/tenant, auditing, session lifetimes, and dual control according to risk.

## 7. Permissions and Terms to Distinguish

| Term | Real Question | Consequence |
| --- | --- | --- |
| Exportable via `getEncoded` | Can raw/DER bytes be retrieved via the Java API? | Enables copying/re-importing when permitted |
| Non-extractable | Does the device forbid extracting the key via all policy-governed mechanisms? | Depends on token/HSM and key-creation attributes |
| Sensitive | Does the device conceal private attributes? | Does not imply all operations are forbidden |
| Sign/decrypt/derive permission | Which operations may the key execute? | Independent permissions; never infer from key type |
| Wrappable | Is exporting **wrapped under a KEK** allowed? | May have dedicated policies for wrapped export |
| Migratable/backup | Does a mechanism exist for HSM/cluster backup or restore? | Not automatically available on non-exportable keys |
| Destroyable/deletable | Can the key be revoked/destroyed in the backend? | Deleting a Java object reference does not destroy the backend key |

In PKCS#11, attributes include `CKA_EXTRACTABLE`, `CKA_SENSITIVE`, `CKA_SIGN`, `CKA_DECRYPT`, `CKA_WRAP`, and `CKA_UNWRAP`; the **full set of attributes and constraints** on the token determines behavior. Never claim a single flag suffices without reviewing standard/vendor policies and wrap/trusted-key rules.

`Cipher.wrap(key)` belongs to JCE cipher wrap mode. It cannot magically **bypass** a non-extractable policy; the backend will reject it if wrapping export is disallowed. Conversely, some keys allow wrapped migration only to a trusted KEK: that is **controlled protected export**, not unrestricted raw export.

## 8. Key Lifecycle in the Two Models

| Lifecycle Stage | Software Exportable | Provider-Bound / Non-Extractable |
| --- | --- | --- |
| Creation | Software `KeyGenerator`/`KeyPairGenerator` or valid raw material | Generate **directly on token/HSM/KMS** with non-extractable policy from start |
| Import | `SecretKeySpec`, `KeyFactory` per format | Import via backend APIs and key attributes; not just creating a `KeySpec` |
| Storage | PKCS12/wrapped bytes/secret storage; protect files/backups | Application stores key ID/alias; backend holds material |
| Usage | Software provider; raw keys can reach the heap | Engine/provider or SDK executes operations via key handle and permissions |
| Backup/restore | Create protected copies/wrapped backups | Vendor HSM cluster/backup/HA mechanisms, sometimes disallowing export |
| Rotation | Create new version, rewrap/re-encrypt, manage old keys | Backend issues new version/alias; old key still needed to read authorized legacy data |
| Destruction | Purge all raw copies, files, backups, versions | Backend revoke/delete and session handling; GC does not destroy key material |

**If policy requires “the private key never leaves the HSM”:** generate the key **inside the HSM** from the outset with matching attributes. You cannot claim that property if you generated the key in Java software and later imported it: raw material already existed outside.

**Backups are an architectural requirement:** a non-exportable key with no HA/backup plan can be lost permanently when a token fails, leaving historical ciphertexts undecryptable. Never impose a non-exportable rule while forgetting a valid recovery plan. Supporting backups may require multiple hardware units and vendor mechanisms, which is not the same as allowing raw export.

**Replacing keys:** every ciphertext/signature should carry a key ID/version or metadata to locate the exact key. A new key does not automatically decrypt data encrypted under the old key; retain old versions for their retention window or execute controlled re-encryption/rewrapping. Never delete an old key before verifying migrated data volume.

## 9. Designing APIs That Do Not Force Every Key into `byte[]`

A service should generally request an **operation**, not a raw key:

```java
// Illustrative API design, not a standalone program.
interface SigningGateway {
    byte[] sign(String keyId, byte[] message) throws Exception;
}

interface DecryptionGateway {
    byte[] decrypt(String keyId, byte[] ciphertext,
                   byte[] associatedData) throws Exception;
}
```

Implementations may use software `Signature.initSign(privateKey)`, an HSM provider with a private key handle, or a cloud KMS SDK RPC. Callers never need `privateKey.getEncoded()`. When a fingerprint is required, use the **public key** or a trusted key ID; **never export a private key just to print a hash/private fingerprint**.

Persist appropriate metadata: provider/backend identifier, algorithm, key ID, key version, allowed purposes, and rotation details. Avoid storing a handle's class name as a durable identifier; token sessions expire and provider objects may not survive restarts. After a restart, look up the key again by alias/key ID and backend authentication policy.

`KeyStore` or provider APIs do not require sharing one global instance across the entire system: cryptographic engines like `Cipher`, `Mac`, and `Signature` hold mutable state and should not be shared across threads/requests without explicit thread-safety contracts. When a provider times out, apply operation-appropriate retry/idempotency handling and never silently fall back to software to extract secrets.

## 10. Comparing Trade-Offs and Choosing a Model

| Criterion | Exportable Software Key | Provider-Only Key |
| --- | --- | --- |
| Portability across providers | Usually high with standard raw/DER formats | Depends on vendor, sessions, SDK, and migration policies |
| Control over raw extraction | Process can read/copy raw bytes when allowed | Backend can genuinely forbid raw extraction |
| Backup/recovery | Easy to copy, though many copies need protection | Backups can be complex; requires proper HA/clustering |
| Speed and latency | Local software is usually fast for high volume | Hardware/RPC introduces throughput/latency/quota constraints |
| Supported algorithms | Defined by JDK/software providers | Defined by firmware/token mechanisms/service APIs |
| If process is compromised | Key can be stolen and used offline | Attacker can abuse permitted sign/decrypt calls, yet extracting raw keys is harder with proper policy |
| Operational complexity | Keystore/secret manager, filesystem, backups, key rotation | IAM, PINs, sessions, audits, availability, key ceremonies, disaster recovery |

**No single option fits every scenario.** CA/payment-gateway signing keys, master KEKs, or critical root keys usually warrant stronger custody than a short-lived session key inside an isolated process. Choose based on the asset being protected, threat model, lifetime, latency, recoverability, and compliance.

## 11. Common Mistakes and How to Handle Them

| Symptom | Cause | Remedy |
| --- | --- | --- |
| `NullPointerException` after `getEncoded()` | Opaque key legitimately returns `null` | Check for `null`; invoke provider operations instead of forcing export |
| `InvalidKeyException` at `Cipher.init` or `Signature.initSign` | Wrong key type/provider, or policy forbids the operation | Use the matching provider/mechanism and key usage |
| `UnrecoverableKeyException`, `KeyStoreException` | Wrong alias, entry password/PIN, store type, or policy | Check store type, credentials, and session |
| `NoSuchAlgorithmException` / `NoSuchProviderException` | Algorithm/provider not configured or unsupported | Verify runtime environment and capabilities |
| `getFormat()==null` | Provider exposes no portable encoding | Never force `KeyFactory` to import non-existent bytes |
| Treating `PKCS12` as an HSM | Confusing a password-protected file with a hardware token | Verify key custody location and backend policy |
| Implementing a custom `SecretKey` returning `null` and expecting it to work | No provider backs that handle | Use a real backing API/provider |
| Wrapping a key with `Cipher.wrap` and getting rejected | Key has non-extractable/wrapping restrictions | Follow policy; do not bypass via raw export |
| New key cannot decrypt old ciphertext | Missing key ID/version management or deleted old key | Plan versioning, rewrapping, or re-encryption |
| HSM private key abused despite being non-exportable | Service allowed to sign/decrypt attacker-chosen inputs | Enforce business authorization, auditing, and rate limits |
| Wiping `byte[]` and assuming the key is gone | Key object/provider still holds copies | Restrict export and manage lifecycle through the backend |
| Token/session restart invalidates handle | Handle bound to session/backend state | Re-resolve by alias/key ID and re-authenticate |
| KMS only exposes RPC yet code forces `KeyStore` | No matching JCA bridge exists | Use the official SDK/adapter |
| Auto-downgrading to software when HSM fails | Fallback breaks non-extractable policy | Fail closed, raise alerts, follow escalation procedures |

### Deployment Checklist

- [ ] Choose exportable vs. non-exportable **before generating the key**, based on threat model and backup needs.
- [ ] Know the exact `KeyStore` type/provider/backend rather than guessing from API names.
- [ ] Handle `getEncoded()==null` intentionally; never fabricate empty keys or bypass with raw export.
- [ ] Never log or serialize raw private/secret keys; minimize copies and memory exposure.
- [ ] Select a provider compatible with the key handle and operation; verify usage policies.
- [ ] Enforce authorization by key ID, tenant, operation, and business context, with audits and rate limits.
- [ ] Understand wrapped export vs. raw export; never use `wrap` to circumvent token policies.
- [ ] Maintain key versions, lifecycle states, rotation, rollback, HA/backups, and disaster-recovery drills.
- [ ] Test disabled keys, HSM unavailability, wrong PINs, missing aliases, and provider mismatches.
- [ ] Revoke/destroy keys at the backend; never equate clearing a Java variable with destroying a device key.

## 12. Self-Check Questions

1. **Does `getEncoded()==null` prove a key lives in hardware?** No; it only means that method provides no encoded bytes.
2. **Will SunJCE accept a mock `SecretKey` returning `null` as an HSM key?** No; it lacks key material or a handle recognized by the provider.
3. **How many bytes is a `RAW` software AES-256 key?** 32 bytes.
4. **What formats are RSA public and private keys commonly exported in?** Public: `X.509` SPKI; private: `PKCS#8` DER.
5. **Does wiping the array returned by `getEncoded()` destroy the original key object?** No; the original key/provider keeps its own state.
6. **Does password-protected PKCS12 mean non-extractable?** No; loaded keys can still support `getEncoded()`, as shown in the demo.
7. **Does a key with only `CKA_SIGN` automatically allow `decrypt`?** No; operation policies are independent.
8. **Can `Cipher.wrap` extract any opaque key?** No; it depends on key extraction/wrapping policies and engine support.
9. **Should a private key that “never leaves the HSM” be generated in software first and imported into the HSM?** No; that violates “never.”
10. **Does a Cloud KMS always return a `java.security.PrivateKey` usable with JCE?** No; some KMS offerings provide only SDK/RPC APIs.
11. **If raw keys cannot be exported, can an attacker cause no harm?** False; they can still abuse `sign/decrypt` if authorized to invoke those calls.
12. **What happens if an HSM holding a non-exportable key is lost with no backup?** Encrypted data may become permanently unrecoverable.
13. **What role do key ID/version play during rotation?** Resolving the right key for legacy records or identifying records needing migration.
14. **How do you verify a key is truly non-extractable?** Check backend/token policy and test permitted/forbidden operations in security verification, not solely via `getEncoded()`.
15. **When designing an HSM/KMS integration API, should you pass raw bytes or request operations?** Prefer operation interfaces taking a key ID/handle, minimizing raw key exposure in the application.

## Official API Documentation (Java SE 21) and References

- [Key: getAlgorithm, getFormat, getEncoded](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Key.html)
- [SecretKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/SecretKey.html)
- [PrivateKey and PublicKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/PrivateKey.html)
- [KeyGenerator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KeyGenerator.html)
- [SecretKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html)
- [KeyFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyFactory.html)
- [KeyStore, SecretKeyEntry, and PasswordProtection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html)
- [Provider](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Provider.html)
- [Java PKCS#11 Reference Guide](https://docs.oracle.com/en/java/javase/21/security/pkcs11-reference-guide1.html)
- [Cipher and wrap/unwrap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)
- [Signature](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html)
- [Destroyable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/Destroyable.html)
