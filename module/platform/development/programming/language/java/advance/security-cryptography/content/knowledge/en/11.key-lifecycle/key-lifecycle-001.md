# 11.1. Classifying Data Keys, Key-Wrapping Keys, and Signing Keys by Responsibility

## Lesson Objectives

In a Java system that uses cryptography, the word “key” can refer to multiple kinds of secrets with **different responsibilities and compromise consequences**. You should not use a single AES key for everything, nor treat a digital signing private key as a “stronger encryption key.” A proper design must clearly separate:

1. **Data Encryption Key (DEK)**: directly encrypts/decrypts application data.
2. **Key Encryption Key (KEK)**, also called a *key-wrapping key*: protects DEKs or other key material during storage/transport.
3. **Signing key**: a private key that creates digital signatures, paired with a public key used to verify message origin/integrity.

After this lesson, you will be able to accurately identify each key's role, pair it with the appropriate JCA operation, design a basic **envelope encryption** flow, verify signed data, choose where keys are stored and who has access, as well as distinguish between **rewrapping a KEK**, **re-encrypting a DEK**, and **replacing a signing key**.

The examples use **Java 17+**, AES-GCM for data encryption, AES Key Wrap (RFC 3394) for wrapping DEKs, and RSA-PSS for signing a record. The examples use software keys generated in RAM to illustrate the API, **not** a complete production key management system.

## 1. Three Key Types Solve Three Different Questions

| Role | Question It Solves | Typical Key and Operation | Protected Target |
| --- | --- | --- | --- |
| **DEK** — data key | “Who can read the confidential content?” | AES `SecretKey`; `Cipher.getInstance("AES/GCM/NoPadding")`, `ENCRYPT_MODE`/`DECRYPT_MODE` | Plaintext of a file, record, blob, or field |
| **KEK** — key-wrapping key | “Who can recover/use the DEK stored in wrapped form?” | AES-KEK with `Cipher.getInstance("AESWrap")`, `WRAP_MODE`/`UNWRAP_MODE`; or another approved wrapping/transport mechanism | **Key material** of a DEK or subkey |
| **Signing key** — signature key | “Was the message/record signed by the party controlling the trusted private key?” | RSA/EC/EdDSA private key via `Signature`; corresponding public key using `verify` | Integrity and signing-origin authentication of the signed message/metadata |

**Commonly confused statements:**

- A DEK **encrypts data**, while a KEK **encrypts/wraps keys**. Even though both may be 128/256-bit AES keys, their roles, access scopes, lifetimes, and rotation procedures are **different**. Sharing “the same AES algorithm” does not make their responsibilities interchangeable.
- A **private signing key** is secret; a **public verification key** can be distributed to verifiers, but **how it is bound to a trusted identity** must still be verified. A public key does not help decrypt a DEK.
- A digital signature **does not keep content confidential**. Authenticated encryption with AES-GCM ensures that ciphertext cannot be modified without detection (when the key/nonce/AAD are used properly), but it **does not by itself prove the sending organization's identity** to recipients who also hold the DEK. These are two different protection services.
- An **HMAC key** is a symmetric key that authenticates data via `javax.crypto.Mac`. HMAC provides authentication between parties sharing the secret, but it is **not** a private signing key used with `Signature` and public-key verification. Do not call an HMAC key an “RSA signing key” or assume HMAC has public-verifiability properties.
- A **Key Derivation Key (KDK)/master key** may be a fourth type, used to derive keys via a KDF. Do not assume by default that a master key is simultaneously a DEK, KEK, and signing key; proper domain separation must be designed according to the primitive/protocol.

NIST SP 800-57 Part 1 classifies key types by **cryptographic function**, along with dedicated lifecycle and protection aspects. An important principle is **limiting a key to its granted purpose**, which narrows the damage if a key is compromised and simplifies auditing, revocation, and authorization.

## 2. Understanding DEKs (Data Encryption Keys) Properly

**Single responsibility under policy:** encrypt and decrypt data at a specific boundary (document, storage object, tenant, or session; depending on architecture).

Example of a document storage system:

- Generate a random AES-256 or AES-128 DEK for **one document**.
- Generate an appropriate nonce/IV for each encryption using AES-GCM; a common configuration is a **12-byte nonce** and 128-bit tag.
- Encrypt plaintext: `Cipher.getInstance("AES/GCM/NoPadding")`, `init(ENCRYPT_MODE, dek, new GCMParameterSpec(128, nonce))`, optionally `updateAAD`, then `doFinal(plaintext)`.
- Store only the ciphertext, nonce, and required metadata alongside the **wrapped DEK**; never store a plaintext DEK unprotected next to the ciphertext.
- When reading, only components with data access rights and appropriate unwrap permissions may obtain the DEK and decrypt.

**DEK scope is a security choice:** one DEK per object isolates impact if a single DEK is compromised; one DEK per tenant reduces key count but widens the blast radius. The decision must weigh data size, traffic volume, authorization rules, performance, and re-encryption procedures.

**AES-GCM caveats:** strictly avoid repeating **(DEK, nonce)** across two different encryptions; generating a fresh random DEK per object reduces risk, but **does not eliminate the unique-nonce requirement** if the same DEK is used multiple times. Storing/transmitting the nonce alongside the ciphertext is normal because a nonce is not a key; protect integrity and binding according to the protocol. If the DEK/nonce/AAD/tag is wrong, decryption must fail and the application must not use any plaintext before `doFinal` succeeds verification.

A DEK typically needs to be present where **the encryption/decryption operation actually executes**. If run in software inside an application, a plaintext DEK may briefly exist in RAM, so restrict logging, heap dumps, telemetry, cross-service transfer, and lifetime. An HSM/KMS can perform the cryptographic operation directly or issue a plaintext DEK to the client depending on the API; never assume that simply “using KMS” means the DEK never leaves the KMS.

## 3. Understanding KEKs (Key Encryption Keys) Properly

**Responsibility:** protect other keys, such as a DEK, when those keys must be stored in a database, object metadata, or transferred across a trust boundary. KEKs are typically managed more centrally than DEKs and can wrap **many DEKs**.

A system may use:

- A **symmetric KEK** (AES) and the **AES Key Wrap** standard per RFC 3394/NIST SP 800-38F, or AES Key Wrap with Padding per RFC 5649.
- **Public key wrapping/transport** when receiving data via a public key; specific mechanisms (e.g., RSA-OAEP) have their own formats and constraints. Do not use raw RSA or a shared RSA signing key for “signing and key wrapping.”
- A **KMS/HSM wrapping key** with a `wrap/unwrap` usage policy, key ID, version, and audit, where the application does not possess the plaintext KEK when the provider/HSM supports this API.

In Java 17, `Cipher.getInstance("AESWrap")` corresponds to AES-KW (RFC 3394), listed in the Java Standard Algorithm Names documentation. `Cipher.getInstance("AESWrapPad")` corresponds to AES-KWP (RFC 5649). A specific environment/provider may not implement every name; always check support and test interoperability.

Symmetric wrapping diagram:

```text
DEK (secret key bytes / key handle)
      |
      | Cipher AESWrap + KEK (more confidential / management tier)
      v
wrapped DEK (key blob ciphertext) ---> can be stored alongside data ciphertext
      |
      | only authorized actors may UNWRAP via KEK
      v
recovered DEK -> used with the permitted data encryption algorithm
```

**Important properties:**

- A **wrapped DEK is not a password**, not data ciphertext, and cannot be used directly as a DEK. It is a blob protecting **key material**.
- Wrapping a KEK under another KEK tier (hierarchy) or a KMS/HSM root key is a common pattern, but **dependency cycles must be avoided** so there is always an available root key for recovery.
- Standard AES-KW performs an **integrity check** on the key data during unwrap; it does not automatically bind full details such as *tenant, object, algorithm, usage policy, key ID* unless the protocol designs a binding mechanism. It does not replace metadata authentication, access control, logging, or a trust model.
- RFC 3394 AES-KW requires key data input to be at least two 64-bit blocks and a multiple of 64 bits. A 16-byte AES-128 DEK satisfies this, typically producing a 24-byte wrapped blob. When wrapping key data of arbitrary size, choose a suitable primitive such as AES-KWP rather than ad-hoc padding.
- A KEK may be **non-exportable** in plaintext from an HSM/KMS. In that case Java `Key.getEncoded()` may return `null` and code relying on exporting raw KEK bytes will fail; use supported key handles/provider integration instead of trying to extract the key.
- An overly broad KEK (shared across every tenant and every application) creates a large blast radius. Partitioning KEKs by policy and key hierarchy helps limit impact, though it also increases the number of metadata records/permissions to manage.

Do not call `Cipher.getInstance("AES")` with unspecified provider defaults to “roll your own key wrapping”; use a wrapping primitive with explicit integrity checking supported by your KMS and standard specifications.

## 4. Understanding Signing Keys Properly

An **asymmetric signing key** pair consists of:

- **Private signing key:** used only by signers granted the `sign` permission. It should be stored in a KeyStore/HSM/KMS supporting the appropriate algorithm and policy. If compromised, an attacker can forge signatures within the key's trust scope.
- **Public verification key:** used for `verify`, and can be distributed widely, but must be bound to a trusted identity/key ID via a certificate chain/trust store, key pinning, or controlled configuration distribution.

Java:

```java
Signature signer = Signature.getInstance("RSASSA-PSS");
signer.initSign(privateSigningKey);
signer.setParameter(pssProfile);
signer.update(bytesToSign);
byte[] signature = signer.sign();
```

This is a **snippet**, assuming `privateSigningKey`, `pssProfile`, and `bytesToSign` have already been created; imports and exception handling must match your application context. Another option is `Signature.getInstance("Ed25519")` when relevant systems and policies support it; never change algorithms arbitrarily between signer and verifier.

**Choosing the right data to sign:** if the system needs to prove a specific object version including its metadata, define a **canonical record** containing version, algorithm IDs, key IDs, nonce/AAD, wrapped DEK, and ciphertext, and sign **the entire canonical byte sequence**. If you only sign the ciphertext while ignoring control fields, an attacker can modify metadata without invalidating the signature. Each field's length/encoding must be specified to avoid ambiguity: `"ab"+"c"` and `"a"+"bc"` yield the same byte sequence under naive concatenation.

**Signatures and AES-GCM tags are different:** a GCM tag confirms that a decryptor holding the DEK received the expected ciphertext/AAD, but it does not prove “who the sender is” when multiple actors hold the DEK; a public signature is tied to a private signing key and verified by parties holding a trusted public key. If data only needs confidentiality and tamper detection within an internal store, AES-GCM with strict access control may suffice; not every object requires a signature. Decide based on trust boundaries, not on a gut feeling that “more algorithms are always better.”

**A signing key should not be used as a KEK.** Because an RSA private key uses the `PrivateKey` type, developers may mistakenly think “having RSA means it can both sign and decrypt.” Using one key pair for both signing and key transport mixes permissions, cryptoperiods, and compromise impact. Use separate key pairs, algorithms, certificate KeyUsage extensions, and policies per purpose.

## 5. Comparing Permissions, Lifecycle, and Blast Radius

| Aspect | DEK | KEK | Signing private key |
| --- | --- | --- | --- |
| Principal using it | Workload encrypting/decrypting the specific object | Authorized wrapping/unwrapping service | Authorized signer |
| Permitted operations | `encrypt`, `decrypt` payload | `wrapKey`, `unwrapKey`; may be restricted per tenant/app | `sign`; public counterpart used for `verify` |
| Typical scope | Object/field/segment/tenant | Group of DEKs or KMS boundary | Application/organization identity and signing policy |
| Long-term storage | **Wrapped DEK**, never plaintext next to data | Protected KMS/HSM/KeyStore, non-exportable key handle where appropriate | Protected HSM/KMS/KeyStore; public key/cert can be distributed |
| If compromised | Data within the DEK's scope may be decrypted; needs a new DEK/re-encryption | Many wrapped DEKs may be exposed; may require bulk rekey/re-encryption depending on impact | Attacker can forge signatures for the subject; revoke trust, replace key, investigate signed records |
| During routine rotation | Replace DEK then **re-encrypt data** | Replace KEK and **rewrap DEK** (not necessarily re-encrypting payload) | Replace signing key, update public key/certificate/trust and verification policy |
| When historical archive/reads are needed | Retain DEK recovery path per retention policy | Retain old KEK version within limits for unmigrated wrapped DEKs | Retain verification public key/certificate and trust history to verify old signatures |

**Do not treat the “routine rotation” row as an incident response procedure for compromise.** For example, if a plaintext DEK has been compromised, simply replacing the KEK does not revoke read access for someone who already holds the DEK; you must evaluate **replacing the DEK and re-encrypting the payload**. If a KEK has been compromised, an attacker may have unwrapped DEKs in the past; rewrapping with a new KEK **does not erase the DEK copies the attacker already obtained**. You must evaluate data scope, key versions, and re-encryption/incident response steps.

### Key IDs, Versions, and Scope

Names like `dekId`, `kekId`, and `signingKeyId` are **routing metadata**, not secrets, and do not represent authorization. A server must never grant unwrap permission merely because a client sent a valid `kekId`. Every operation must check actor identity, tenant/object scope, key state (active/decrypt-only/retired), usage policy, and audit logging.

When rotating a KEK, `kek-v1` and `kek-v2` may coexist during a transition period; the **key ID must point precisely to the version** matching the wrapped DEK. When a signing key changes, existing verifiers may still need the old public key to verify valid signatures created earlier, depending on retention and security incident policies.

## 6. Envelope Encryption: How Do the Three Roles Work Together?

A single-object diagram:

```text
                 ┌─ Random DEK ────────────────────────┐
                 │                                      │
  plaintext ───> AES-GCM.encrypt(DEK, nonce, AAD)       │
                 │                   │                  │
                 v                   v                  v
         ciphertext+tag         nonce/AAD         AESWrap(KEK, DEK)
                                                      │
                                                      v
                                                  wrappedDEK
                 │                   │                  │
                 └──────────┬────────┴──────────────────┘
                            v
               canonical envelope bytes
          (version, algorithms, key IDs,
           nonce, AAD, wrappedDEK, ciphertext)
                            |
          Sign(privateSigningKey, envelope)
                            |
                            v
       Store: envelope + signature + signer key reference

Recipient:
  - check access permissions + signer public-key trust
  - verify signature over EXACT envelope bytes per policy
  - select KEK via server-side authorization, unwrap DEK
  - AES-GCM.decrypt(DEK, nonce, AAD, ciphertext+tag)
  - release plaintext only after tag verification succeeds
```

Concrete steps:

1. **Generate a DEK** using an appropriate CSPRNG/`KeyGenerator`; decide the DEK's scope (per object or otherwise).
2. **Encrypt the payload** using an AEAD such as AES-GCM with a unique nonce for the (DEK, nonce) pair, and AAD containing stable context that must be authenticated (such as object/tenant/version).
3. **Wrap the DEK** using a KEK with wrap permission; store `wrappedDEK`, `kekId`, and `wrapAlgorithm`.
4. **Build an envelope with a canonical byte format** containing version, algorithm IDs, identifiers, nonce, AAD, wrapped key, and ciphertext. Do not rely on string concatenation with ambiguous boundaries.
5. **Sign the envelope** if the problem requires signing-origin authentication. The signer needs the private signing key; the signature is stored along with the signer key ID and required trust information.
6. **When reading**, verify authorization and the signature **over the exact signed bytes** before unwrapping the DEK with the server-authorized KEK. Then decrypt the data, verify the GCM tag, and only then pass plaintext into the system.
7. **Log selectively:** actor, key IDs, operation, object reference, timestamp, and outcome. Never log plaintext, raw DEK, KEK, signing private key, or unnecessary wrapped key blobs.

**Important note on rewrapping:** if you include `kekId` or `wrappedDEK` in the **AAD of the AES-GCM payload**, changing the KEK/wrappedDEK will change the AAD and invalidate the old tag. When you need to rewrap **without re-encrypting data**, design payload AAD to contain only metadata that is **invariant across rewraps** (e.g., tenant, object, content version), while wrapping fields can be authenticated via **a signature/another protected metadata mechanism**. Because the signature in the example covers wrapping fields, after a rewrap you must **generate a new authorized manifest signature**; do not modify signed metadata while keeping the old signature.

### Example Long-Term Stored Record

```json
{
  "formatVersion": 1,
  "objectId": "doc-42",
  "contentVersion": 3,
  "dataAlgorithm": "AES/GCM/NoPadding",
  "nonce": "<base64url>",
  "aadContext": "tenant-7|doc-42|v3",
  "ciphertextAndTag": "<base64url>",
  "wrappedDek": "<base64url>",
  "kekId": "tenant-7-kek-v2",
  "wrapAlgorithm": "AESWrap",
  "signatureAlgorithm": "RSASSA-PSS",
  "signingKeyId": "signer-v4",
  "signature": "<base64url>"
}
```

Values inside `<...>` are **example placeholders**, not real credentials. This record only illustrates **the fields**; before signing, you must specify **canonical byte serialization**, length-prefix/canonical JSON rules, versioning, and ordering, rather than signing an ambiguous JSON object and hoping later serialization preserves identical bytes. Across multiple environments, explicitly record PSS digest/MGF1/saltLen/trailer or use a protocol-fixed profile (PS256).

A signature stored inside a record **does not verify itself**: you must have a trusted public key independent of untrusted input and must not arbitrarily accept an algorithm/key ID chosen by an attacker.

## 7. Complete Java 17+ Example: DEK + KEK + Signing Key

The following example demonstrates all **three roles** together in a single process:

- Two 128-bit AES keys **generated independently**: `dek` for AES-GCM data, `kek` for AES Key Wrap.
- An independent 2048-bit RSA key pair for RSASSA-PSS signatures with SHA-256, MGF1-SHA256, and a 32-byte salt.
- `pack(...)` uses a **4-byte big-endian length prefix** on each field to reduce the risk of ambiguous signature input. The signed record includes algorithm labels, key IDs, nonce, AAD, wrapped DEK, and ciphertext.
- DEK recovery, data decryption, and signature verification are all performed. Modifying a byte of the signed record must cause verification to return false.

Save file **`KeyRolesDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class KeyRolesDemo {
    private KeyRolesDemo() {}

    private static byte[] pack(byte[]... parts) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            for (byte[] part : parts) {
                out.writeInt(part.length);
                out.write(part);
            }
        }
        return bytes.toByteArray();
    }

    private static boolean verify(PublicKey key, PSSParameterSpec spec,
            byte[] message, byte[] signature) throws Exception {
        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.initVerify(key);
        verifier.setParameter(spec);
        verifier.update(message);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator keys = KeyGenerator.getInstance("AES");
        keys.init(128);
        SecretKey dek = keys.generateKey();
        SecretKey kek = keys.generateKey();

        byte[] payload = "secret document".getBytes(StandardCharsets.UTF_8);
        byte[] aad = "tenant=42;purpose=report".getBytes(StandardCharsets.UTF_8);
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        Cipher dataEncrypt = Cipher.getInstance("AES/GCM/NoPadding");
        dataEncrypt.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(128, nonce));
        dataEncrypt.updateAAD(aad);
        byte[] sealed = dataEncrypt.doFinal(payload);

        Cipher keyWrap = Cipher.getInstance("AESWrap");
        keyWrap.init(Cipher.WRAP_MODE, kek);
        byte[] wrappedDek = keyWrap.wrap(dek);

        Cipher keyUnwrap = Cipher.getInstance("AESWrap");
        keyUnwrap.init(Cipher.UNWRAP_MODE, kek);
        SecretKey restoredDek = (SecretKey) keyUnwrap.unwrap(
                wrappedDek, "AES", Cipher.SECRET_KEY);

        Cipher dataDecrypt = Cipher.getInstance("AES/GCM/NoPadding");
        dataDecrypt.init(Cipher.DECRYPT_MODE, restoredDek,
                new GCMParameterSpec(128, nonce));
        dataDecrypt.updateAAD(aad);
        byte[] restored = dataDecrypt.doFinal(sealed);

        KeyPairGenerator signingKeys = KeyPairGenerator.getInstance("RSA");
        signingKeys.initialize(2048);
        KeyPair signingPair = signingKeys.generateKeyPair();

        PSSParameterSpec pss = new PSSParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                32, PSSParameterSpec.TRAILER_FIELD_BC);

        byte[] record = pack(
                "AES/GCM/NoPadding".getBytes(StandardCharsets.US_ASCII),
                "AESWrap".getBytes(StandardCharsets.US_ASCII),
                "kek-v1".getBytes(StandardCharsets.US_ASCII),
                "sign-v1".getBytes(StandardCharsets.US_ASCII),
                nonce, aad, wrappedDek, sealed);

        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.initSign(signingPair.getPrivate());
        signer.setParameter(pss);
        signer.update(record);
        byte[] signature = signer.sign();

        byte[] modified = record.clone();
        modified[modified.length - 1] ^= 1;

        System.out.println("dekBytes=" + dek.getEncoded().length);
        System.out.println("kekBytes=" + kek.getEncoded().length);
        System.out.println("wrappedDekBytes=" + wrappedDek.length);
        System.out.println("ciphertextBytes=" + sealed.length);
        System.out.println("keyRecovered=" +
                Arrays.equals(dek.getEncoded(), restoredDek.getEncoded()));
        System.out.println("dataRecovered=" + Arrays.equals(payload, restored));
        System.out.println("signatureBytes=" + signature.length);
        System.out.println("signatureValid=" +
                verify(signingPair.getPublic(), pss, record, signature));
        System.out.println("modifiedRecordAccepted=" +
                verify(signingPair.getPublic(), pss, modified, signature));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 KeyRolesDemo.java
java KeyRolesDemo
```

**Verified stdout on a JDK supporting the listed algorithms:**

```text
dekBytes=16
kekBytes=16
wrappedDekBytes=24
ciphertextBytes=31
keyRecovered=true
dataRecovered=true
signatureBytes=256
signatureValid=true
modifiedRecordAccepted=false
```

The sizes are straightforward: `"secret document"` is 15 UTF-8/ASCII bytes; AES-GCM with a 128-bit tag produces **15 + 16 = 31 bytes** of ciphertext+tag. The wrapped AES-128 DEK has 16 bytes of key material, and RFC 3394 AES-KW adds 8 bytes of overhead for **24 bytes**. An RSA-2048 signature is **256 bytes** long. Secret/key/nonce contents and signature bytes **change across runs**, while the boolean/length values shown in stdout are deterministic in compatible providers.

### Analysis by Responsibility Boundary

1. `KeyGenerator` generates **two independent AES keys**. Although both share the `SecretKey` interface, `dek` only goes through the data cipher and `kek` only goes through the wrapping cipher. The Java object type `SecretKey` **does not enforce a prohibition against misuse**; this is merely a code convention. Production requires IAM/KMS/HSM policies and access control.
2. `dataEncrypt` uses the **DEK**, 12-byte nonce, and AAD. `doFinal` produces ciphertext+tag. The output does not include the plaintext DEK.
3. `keyWrap` uses the **KEK** in `WRAP_MODE`, taking `dek` as input and producing the wrapped key blob as output. `keyUnwrap` uses the same KEK in `UNWRAP_MODE` and reconstructs the AES `SecretKey`. It does not need to know the document's plaintext.
4. `dataDecrypt` uses the **unwrapped DEK**, along with the nonce and AAD. `restored` is accepted only after the GCM tag has been verified.
5. `signingPair` is an RSA key pair **unrelated** to DEK/KEK. The private key signs the envelope bytes; the public key verifies. The code neither uses RSA to wrap the AES key nor uses an AES key to simulate a digital signature.
6. `pack` encodes field boundaries with an `int` prefix. This illustrates deterministic byte input; version/headers, trusted fields, and size limits during parsing still need to be added in a production protocol.
7. `modifiedRecordAccepted=false` proves that flipping the last byte of the signed record fails verification against the original signature. **Verifying with a public key supplied by an attacker is meaningless for identity**; the demo holds the public key in the same process solely to demonstrate how to call the API.
8. Because software AES keys in the demo can be exported with `getEncoded()`, comparing raw bytes works. With HSM-backed nonexportable keys, `getEncoded()` may return `null`; perform operations via key handles rather than forcing key export for testing.

In the demo code, the decryptor already has `kek` and the private signing key resides only with the signer. When separating into multiple services, **do not pass the private signing key to verifiers** and **do not grant plaintext KEK access to services that only need to verify signatures**.

## 8. Replacing a KEK Does Not Necessarily Require Re-Encrypting Data

**Rewrap** is the operation of changing a DEK's protection layer. If the DEK is still secure and the ciphertext has not changed, you can unwrap the DEK with the old KEK, rewrap the DEK with the new KEK, and then **atomically write** the new `wrappedDek`/`kekId` metadata.

```text
Before:
 ciphertext = AES-GCM(DEK, plaintext, nonce, AAD)
 wrappedDekV1 = AESWrap(KEK-v1, DEK)

Rewrap:
 DEK = AESUnwrap(KEK-v1, wrappedDekV1)
 wrappedDekV2 = AESWrap(KEK-v2, DEK)

After:
 ciphertext stays unchanged
 payload nonce + AAD stay unchanged
 wrappedDekV2 + kekId=v2 replaces wrappedDekV1
```

Only do this when the payload's AAD **is not altered by KEK metadata**; if changing metadata is included in the AAD, adjust the design or perform the proper re-encryption workflow. If the entire envelope is **signed**, rewrapping changes `kekId`/`wrappedDek` and therefore changes the signed bytes: you must generate a new authorized attestation/signature rather than keeping the old signature as if nothing changed.

### Standalone Java Example of Rewrap

Save **`RewrapOnlyDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class RewrapOnlyDemo {
    private RewrapOnlyDemo() {}

    private static SecretKey newAesKey() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        return generator.generateKey();
    }

    private static byte[] wrap(SecretKey kek, SecretKey dek)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AESWrap");
        cipher.init(Cipher.WRAP_MODE, kek);
        return cipher.wrap(dek);
    }

    private static SecretKey unwrap(SecretKey kek, byte[] wrapped)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AESWrap");
        cipher.init(Cipher.UNWRAP_MODE, kek);
        return (SecretKey) cipher.unwrap(wrapped, "AES", Cipher.SECRET_KEY);
    }

    public static void main(String[] args) throws Exception {
        SecretKey dek = newAesKey();
        SecretKey oldKek = newAesKey();
        SecretKey newKek = newAesKey();

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        byte[] message = "stored record".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(128, nonce));
        byte[] ciphertext = encrypt.doFinal(message);

        byte[] oldWrapped = wrap(oldKek, dek);
        SecretKey recoveredDek = unwrap(oldKek, oldWrapped);
        byte[] newWrapped = wrap(newKek, recoveredDek);

        SecretKey afterRotation = unwrap(newKek, newWrapped);
        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, afterRotation,
                new GCMParameterSpec(128, nonce));
        byte[] restored = decrypt.doFinal(ciphertext);

        System.out.println("oldWrappedBytes=" + oldWrapped.length);
        System.out.println("newWrappedBytes=" + newWrapped.length);
        System.out.println("sameDataKey=" +
                Arrays.equals(dek.getEncoded(), afterRotation.getEncoded()));
        System.out.println("payloadUnchanged=" +
                Arrays.equals(message, restored));
        System.out.println("ciphertextBytes=" + ciphertext.length);
    }
}
```

```bash
javac -encoding UTF-8 RewrapOnlyDemo.java
java RewrapOnlyDemo
```

Stdout:

```text
oldWrappedBytes=24
newWrappedBytes=24
sameDataKey=true
payloadUnchanged=true
ciphertextBytes=29
```

`"stored record"` is 13 UTF-8 bytes and the GCM tag is 16 bytes, making the ciphertext 29 bytes. `sameDataKey=true` proves the DEK **did not change** after unwrap/rewrap, and `payloadUnchanged=true` shows that **the same old ciphertext** can be decrypted using the DEK recovered via the new KEK.

This example has no database, signer, transaction, or permission checks; it only demonstrates the rewrap principle. In production, the commit step must be consistent: `newWrappedDek` and `newKekId` must be updated in **the same transaction/version**, unwrap must be verified as succeeding, and rollback must not break readability. Never delete an old KEK while objects still point to that version.

### Comparing the Three Rotation Workflows

| When changing | Minimum required actions | What **must not** be misunderstood |
| --- | --- | --- |
| **Routine KEK rotation** | Rewrap each DEK that still needs storage, update key ID/metadata atomically, verify readability | It is not necessarily required to replace the DEK or re-encrypt the payload. |
| **DEK rotation** | Generate a new DEK, **decrypt with the old DEK** and **encrypt the payload with the new DEK and a suitable nonce**, wrap the new DEK | Merely changing `wrappedDEK` does not change the actual DEK. |
| **Signing key rotation** | New key pair, distribute new public verification key/cert, update signer key ID and trust policy | You cannot simply “rewrap the private signing key” and consider signer identity/validity transferred. |
| **KEK compromise** | Assess which DEKs may have been unwrapped; may require new DEKs/re-encryption, revoking access, and investigation | Rewrapping after an incident does not make the attacker forget old DEKs. |
| **Signing key compromise** | Revoke/suspend signing privileges, publish/distribute updated trust policy, assess previously issued signatures | Replacing the key does not make previously forged signatures cease to exist. |

Do not apply “delete the old key immediately” as a blanket rule. Each key may need stages **active → decrypt/unwrap/verify only → retired → destroyed** according to retention, legal hold, key compromise, and backup/restore requirements. For long-term archived signatures, retain sufficient public verification material and evidence of trust status at signing time if required by the protocol.

## 9. Access Permissions and Key Storage Locations

Labeling keys “DEK”, “KEK”, and “signing key” in code is not enough. You must build **permission boundaries** so each actor only performs its intended function.

| Actor/service | DEK usage | KEK usage | Signing private key | Signing public key |
| --- | --- | --- | --- | --- |
| Data writer | Encrypt authorized data | Request DEK wrap (via KMS/HSM if applicable) | Sign only if separately authorized | Verify metadata when needed |
| Data reader | Decrypt objects with read permission | Request DEK unwrap under appropriate policy | Not needed | Verify envelope when needed |
| Key management service | Orchestrate generate/wrap/unwrap/rotation without needing to read payload | Administer KEKs per policy | Not by default | May administer trust anchors |
| Signing service | Does not need plaintext DEK | Does not need KEK | Has `sign` permission on keys within authorized scope | Can verify |
| Public verifier | Not needed | Not needed | **Never** | Yes, but must authenticate public key source |

**Production conditions that should be in place:**

- **Policy by key purpose:** only allow encrypt/decrypt, wrap/unwrap, or sign/verify on the matching key. KMS/HSM/APIs may enforce `KeyUsage`/operations; check provider documentation rather than inferring from Java object names.
- **Key identity and version:** each key has a stable ID, key version, algorithm, size, scope/tenant, status, and usage rules. Never use a user-supplied key ID as authorization.
- **Key generation:** use a secure RNG and manage keys with an appropriate system; never hard-code keys in code, container images, Git, secret logs, or spreadsheets.
- **Do not export unnecessarily:** avoid passing KEKs and signing private keys across multiple services; prefer handles inside an HSM/KMS. If a DEK must be exported to an application, restrict its lifetime/caching and access permissions.
- **Audit & incident response:** log `who/what/which key/which object/when` and the outcome of unwrap/sign/rotation, but never log raw keys, plaintext, or private material. Monitor anomalies (spikes in unwrap calls, signer signing out of hours or across tenants).
- **Backup/recovery:** backing up ciphertext **without the ability to recover DEK/KEK** can render data undecryptable. Design controlled key recovery rather than creating floating plaintext backups.
- **Separation of duties:** a person managing key policies is not automatically entitled to read all data, a person with data read access is not automatically allowed to sign on behalf of the organization, and a signer is not automatically allowed to unwrap every tenant.

### Java Types Do Not Equal Key Policy

- `javax.crypto.SecretKey` represents a secret key and can be used for either a DEK or a KEK. Relying on the type alone does not guarantee the **correct purpose**.
- `java.security.PrivateKey`/`PublicKey` form an asymmetric key pair, yet an RSA private key does not enforce a **sign-only** restriction if the backend does not verify policy.
- `java.security.KeyStore` provides storage/retrieval mechanisms for keys and certificates (depending on type/provider); it **does not replace** full IAM, key lifecycle, KMS auditing, and separation of duties.
- `Key.getEncoded()` may return `null` if a key is non-exportable/opaque. Code must handle HSM/PKCS#11 providers without assuming raw key bytes are available.
- X.509 `KeyUsage` metadata can distinguish `digitalSignature`, `keyEncipherment`, and `keyAgreement`; it is useful when processing certificates, but enforcement depends on the verifier/protocol/policy. Never assume a key is automatically valid for a purpose just by seeing a certificate.

## 10. Threats and Incidents: Responding by Key Type

### If a Single Object's DEK Is Compromised

Assess **which object and data versions** could have been read. If that DEK is still in use, generate a different DEK, re-encrypt the data with a fresh nonce, wrap the new DEK, update metadata/signatures accordingly, and revoke read access if needed. Do not assume deleting the key record from the database erases copies already exfiltrated.

### If a Multi-Object KEK Is Compromised

A compromised KEK can allow unwrapping **many DEKs** from previously collected records. Replacing the KEK only protects wrapped DEKs **going forward**; it cannot guarantee prior DEKs were not harvested by an adversary. Evaluate all objects/versions that ever used the KEK, the potential need to re-encrypt with new DEKs, backup retention windows, access history, and incident notification scope. Prioritize maintaining a **key inventory** to trace affected objects without blind scanning.

### If a Signing Private Key Is Compromised

An adversary can create a new signature matching the public key currently trusted by verifiers. Revoke/suspend the key, update the key registry/certificates/trust policy, audit the new signer, and review signed artifacts. **AES-GCM ciphertext remains confidential if DEK/KEK were not exposed**, yet metadata/signature forgery can compromise the trust boundary. Signing timestamps, transparency logs, or a timestamp authority (if present) can be critical when evaluating historical signatures.

### If Metadata/Key IDs Are Tampered With

Do not allow transferring `wrappedDek` from tenant A to tenant B merely by modifying `kekId`. Use server-side authorization and context protection/binding (invariant AAD, appropriate signature, or MAC). When restoring from backup or migrating data, consistency across `kekId`, `wrappedDek`, `dataAlgorithm`, `nonce`, `AAD`, and ciphertext is mandatory.

**Principle:** the same cryptographic primitive can process multiple key types algorithmically, but this **does not remove** the need for authorization and separation of responsibilities in the key management system.

## 11. Common Mistakes and How to Fix Them

| Mistake | Risk | Fix |
| --- | --- | --- |
| Using the same AES key for both data encryption and key wrapping | Mixes purposes, makes limiting blast radius and usage permissions difficult | Generate separate DEK/KEK; separate policies/handles. |
| Storing plaintext DEK alongside ciphertext | Anyone gaining database access can decrypt immediately | Store wrapped DEK under a policy-enforced KEK/KMS. |
| Using a signer private key to transport/wrap DEKs | Violates separation of use and certificate/protocol constraints | Use a dedicated KEK/key transport key. |
| Treating a signature as encryption | Data remains readable in plaintext | Encrypt with a DEK; sign when signer authentication is needed. |
| Treating a GCM tag as a sender-origin signature | Any actor sharing the DEK can produce a valid ciphertext/tag | Use a signature when identity provenance is needed. |
| Sending a public key in the record and trusting `verify=true` | Attacker generates their own key/signature | Authenticate the public key via trust store/certificate/pinning. |
| Letting the client choose `kekId` and unwrapping without checks | Cross-tenant or ACL bypass, creating an oracle | Authorize actor/tenant/object/key usage server-side. |
| Forgetting to bind nonce, wrapped DEK, and algorithm IDs when signing metadata | Metadata can be altered outside signature coverage | Use a canonical envelope and sign all security-critical fields. |
| Reusing (DEK, nonce) with AES-GCM | Risk of breaking security | Use a unique nonce for every encryption under the same DEK. |
| Rewrapping a KEK while keeping the signature over the old wrapped key | Signature no longer matches the new envelope | Re-sign the new version with authorization and preserve the audit chain. |
| Putting a mutable `kekId` in payload AAD and attempting rewrap without re-encrypting | AEAD tag becomes invalid after AAD changes | Design stable AAD or run the full re-encryption workflow. |
| Rotating the KEK after a DEK compromise and declaring things safe | Attacker still possesses the old DEK | Assess scope and rotate DEKs/re-encrypt if needed. |
| Deleting the old KEK before migrating all wrapped DEKs | Permanent loss of ability to decrypt historical data | Use inventory, migration checkpoints, rollback, and retention. |
| Putting raw keys/private material into logs | Secret exposure via observability | Log key ID, operation, and status instead of key material. |
| Assuming Java's `SecretKey` enforces “data-only” by itself | A Java object is not a complete security policy | Use IAM/KMS/HSM usage restrictions and service boundaries. |
| Assuming every key has `getEncoded()!=null` | Fails with non-exportable HSM keys | Use provider-bound `Key` handles and supported cryptographic operations. |
| Using `AESWrap` for arbitrary data/any length | RFC 3394 has specific key data input conditions and purpose | Choose AES-KWP or an appropriate AEAD per standard. |

## 12. Practice Exercises

1. **Classification:** a system managing 10,000 documents has one KEK in KMS and 10,000 wrapped DEKs. One signing private key is used to create manifest attestations. Specify which actors should hold `encrypt/decrypt`, `wrap/unwrap`, `sign`, and `verify` permissions.
2. **Code reading:** in `KeyRolesDemo`, why do `dekBytes=16` and `kekBytes=16` not prove the two keys share the same responsibility? Why is `wrappedDekBytes=24` different from `ciphertextBytes=31`?
3. **Code modification:** flip one byte in the signed `record` and observe `modifiedRecordAccepted=false`. If you substitute a newly generated attacker public key, why does `verify=true` with the attacker's signature fail to authenticate the real sender?
4. **Rewrap practice:** run `RewrapOnlyDemo` and explain why ciphertext/AAD/nonce do not need modification to decrypt via the new KEK; if the entire envelope is signed, which mandatory step must be added?
5. **Metadata design:** list the fields that must be stored to decrypt an object after 3 years when the KEK has rotated multiple times. Which fields are secrets? Which fields must be authenticated/bound?
6. **Compromise:** suppose only the KEK is compromised and an attacker downloaded copies of all wrapped DEKs. Compare the effect of (A) rewrapping the same DEKs versus (B) generating new DEKs + re-encrypting each object.
7. **Misconfigured policy:** a service only needs to verify signatures but has been granted `UNWRAP_MODE` on the KEK. Adjust the IAM/KeyStore/KMS policy to narrow its privileges.
8. **AAD and rewrap:** why does putting `kekId` into AES-GCM AAD make rewrapping harder? Propose a set of invariant metadata to put in AAD and a set of wrapping metadata to cover with the signature.
9. **Multi-tenant:** an API accepts `tenantId` and `kekId` from a request. Propose three validation/authorization steps to prevent tenant A from pointing to tenant B's KEK.
10. **Audit and retention:** an old signing key is now verify-only while an old DEK must still decrypt archived data. Design different key states and revocation procedures for the signing public/private pair compared to the KEK.
11. **Alternative mechanisms:** explain when a system can rely solely on AES-GCM with DEK/KEK without a signing key, and when a digital signature is required to verify a trusted issuer across multiple parties.

**Passing criteria:** accurately explain the three roles; describe how DEK, KEK, and signing private/public keys flow through an envelope; demonstrate by example that rotating a KEK need not alter ciphertext; recognize that a KEK compromise can lead to DEK compromise; and describe appropriate enforcement, metadata, nonce, trust, and rotation per key type.

## References

- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [NIST SP 800-38F — Methods for Key Wrapping](https://csrc.nist.gov/pubs/sp/800/38/f/final)
- [RFC 3394 — Advanced Encryption Standard (AES) Key Wrap Algorithm](https://www.rfc-editor.org/rfc/rfc3394)
- [RFC 5649 — AES Key Wrap with Padding](https://www.rfc-editor.org/rfc/rfc5649)
- [Java 17 Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html)
- [Java 17 `Cipher` — `WRAP_MODE`/`UNWRAP_MODE`, `wrap`/`unwrap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html)
- [Java 17 `Signature` — `initSign`/`initVerify`/`sign`/`verify`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html)
- [Java 17 `Key` — `getEncoded` may return `null`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Key.html)
- [Java 17 `KeyStore` — managing keys and certificates](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html)
