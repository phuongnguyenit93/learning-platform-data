# 11.5 Envelope Encryption and Separating Data Keys from Key-Protecting Keys

## Objectives

This lesson belongs to **11. Key Lifecycle** in Java Advance – security-cryptography. After this lesson, you will be able to:

1. Explain **envelope encryption** and distinguish a **DEK (Data Encryption Key)** from a **KEK (Key Encryption Key)** by role, storage location, access permissions, and lifecycle.
2. Describe the workflow **generate DEK → encrypt data → wrap DEK with KEK → store envelope → unwrap DEK → decrypt data**; understand what may be stored publicly and what must be protected.
3. Understand why **rewrapping a DEK** when rotating a KEK typically avoids decrypting/re-encrypting all data, yet **differs** from rotating a DEK or remediating a key compromise.
4. Use **Java 17+ and AES-GCM** to write a standalone simulation featuring key separation, AAD, nonces, tamper verification, and DEK rewrapping.
5. Apply the design to KMS/HSM with key ID control, multi-tenancy, cryptographic service permissions, rotation schedules, backups, restore testing, and auditing without storing exposed secret keys.

**Limitations of the example:** the Java program below uses two `SecretKey` objects generated **in memory** to illustrate the DEK/KEK layers. It is **not** a real KMS and provides no IAM, HSM, auditing, or key protection against a compromised process. In production, KEKs should be managed by a key management service/KMS or appropriate security hardware; application code should hold only the permissions needed by policy.

## 1. The Problem: Why Not Use One AES Key for All Data?

Suppose a service stores millions of records or files, each encrypted with AES-GCM. The simplest approach is taking **one system-wide AES key** and encrypting every file with it. Yet doing so causes problems:

- Every service needing decryption may have to access **the same key used for all data**, widening the blast radius if the key is compromised.
- Rotating the data encryption key may require reading and re-encrypting massive data volumes, consuming I/O, CPU, and time.
- Enforcing permissions per tenant, document, or application becomes difficult; one over-scoped key can decrypt unrelated assets.
- Tracking key versions, revoking access, backup/restore, and incident recovery become complex.
- Reusing an AES-GCM nonce under the same key severely breaks security. Using one key for massive numbers of encryptions increases operational burden for nonce management and key lifetime.

**Envelope encryption** addresses several of these issues through **key hierarchy**. Typically, data is encrypted with a **dedicated DEK**; the DEK itself is **wrapped/encrypted** under a **KEK** with tighter custody/authorization boundaries. Large payloads can thus be encrypted locally and quickly while the higher-tier key stays centrally managed with restricted access.

This does not mean the model automatically solves everything. If an application is allowed to ask KMS to unwrap every DEK and gets compromised, an attacker can still decrypt all data within that permission scope. Envelope encryption is one component of a secure architecture, not a substitute for least privilege, identity, auditing, nonce policy, and in-memory plaintext controls.

## 2. Two Key Types: DEK and KEK

| Criterion | **DEK — Data Encryption Key** | **KEK — Key Encryption Key** |
| --- | --- | --- |
| Purpose | Encrypt **data content** (files, records, objects, blobs) | **Protect DEKs** (wrap/encrypt/unwrap) |
| Scope | Per object, object group, or session, per policy; narrow scope is usually preferred | Can protect many DEKs; should be bound to tenant, app, environment, role, and key policy |
| Example algorithms | AES-256-GCM (AEAD), with a unique nonce under the same DEK | Properly configured AES key wrap / AES-GCM, or KMS/HSM wrap; appropriate asymmetric schemes may also be used |
| Key generation | Generated via CSPRNG; typically generate a **fresh DEK** when encrypting a new object | Generated/managed inside KMS/HSM or a controlled secret manager/keystore |
| Storage | **Never store plaintext DEK alongside ciphertext**; store the **wrapped DEK** | Keep KEK in a trusted boundary; if KMS/HSM holds it non-exportable, the app only sees a key ID/handle |
| Usage permissions | Used briefly to encrypt/decrypt specific content | Wrap/unwrap permissions, identity binding, key policy, auditing, and quotas |
| Rotation | Changing a DEK typically **requires re-encrypting the data** protected by the old DEK | Changing a KEK can **rewrap DEKs** without altering data ciphertext |
| If compromised | Affects data encrypted under that DEK; blast radius depends on reuse | Can affect many DEKs wrapped under that KEK, including older backups |

**Terminology:**

- **Plaintext DEK:** raw key bytes used directly with AES-GCM to encrypt data; this is a secret.
- **Wrapped/encrypted DEK:** encrypted data containing the DEK and required tag/metadata; it can be stored alongside content ciphertext, yet by itself **is not a directly usable key**.
- **KEK ID / key version:** identifier enabling the system to **locate the right trusted KEK** during unwrap; a key ID is not a secret and **does not grant authorization**.
- **Master/root key:** system-specific name for a higher-tier key, which may itself be the KEK protected by KMS. Do not assume every system must have exactly three tiers.

For example, 10 MiB of data is encrypted with AES-256-GCM under a 32-byte DEK. The KEK only needs to wrap **32 bytes of DEK** (plus wrap overhead), rather than processing all 10 MiB. That yields both performance benefits and separation of duties.

## 3. What Does an Envelope Look Like?

A sound storage design records enough metadata to decrypt **correctly** in the future; illustrative example:

```text
Encrypted Object Envelope
+-------------------------------------------------------+
| envelopeVersion = 1                                   |
| tenantId / objectId / purpose (per protocol)          |
| dataAlgorithm = AES-256-GCM                           |
| dataNonce (12 bytes)                                  |
| dataCiphertext || dataTag (16-byte GCM tag)           |
|                                                       |
| wrappingAlgorithm = KMS-based-wrap / AES-GCM-wrap     |
| kekId = "tenant-A/kek-v3"                              |
| wrapNonce (if required by the wrap scheme)            |
| wrappedDEK || wrapTag (if using AEAD-GCM wrap)        |
+-------------------------------------------------------+
```

Where:

- **dataCiphertext** is the ciphertext of the bulk data, produced using the DEK.
- **wrappedDEK** is the DEK after protection by the KEK; it cannot substitute for the DEK to decrypt data before unwrapping.
- **dataNonce** and **wrapNonce** are two nonces for **two separate encryptions**. Under GCM, nonces must be unique **per key used**. Seeing a nonce in the envelope does not reveal the key (a nonce is not a secret).
- **dataTag / wrapTag** provide AEAD authentication for *each layer* when GCM is used. Tags must never be truncated or dropped arbitrarily.
- **kekId** specifies which **registered and permitted** KEK to use. Never let a payload-declared URL or arbitrary key override the trusted key registry.
- **tenantId**, **objectId**, and **purpose** anchor the record to the right data boundary; fields affecting how content is interpreted must be **authenticated** via AAD or an equivalent mechanism.

Two-tier diagram:

```text
                  DATA PLANE                                KEY PLANE
plaintext data ----------> AES-GCM(plaintext DEK) --> dataCiphertext + dataTag
                                 ^                           |
                                 |                           v
CSPRNG --> plaintext DEK --------+                  store dataNonce + ciphertext
            |                    |
            v                    |
  wrap/encrypt under KEK         |
            |                    |
            v                    |
    wrapped DEK + metadata ------+------> store alongside encrypted object
            ^
            |
      KEK managed by KMS/HSM
       (not inside the object)
```

The diagram illustrates functional separation, not a mandatory server split. Data ciphertext, wrapped DEK, nonces, and metadata may reside together in storage; **it is the KEK and plaintext DEK that must be protected**.

**Beware of “encrypted DEK” versus “DEK”:** calling `getEncoded()` on an AES secret key can expose the **real key** as a byte array. Never store that array in the envelope. The envelope holds only the **wrapped value**; the plaintext DEK is cleared or tightly lifetime-bounded after the operation completes as far as the runtime permits.

## 4. Encryption Flow: Generating a DEK and Wrapping It with a KEK

Steps when creating an object:

1. **Determine policy from a trusted source:** tenant, object ID, purpose, permitted KEK, envelope version, and algorithm. Never let clients impose key IDs outside an allowlist.
2. **Generate a fresh DEK** from a cryptographic RNG, e.g., 32 bytes for AES-256. Never derive a DEK from an object ID, timestamp, weak password, or content hash.
3. **Encrypt the data with the DEK**, typically via `AES/GCM/NoPadding` with a 12-byte nonce unique under that DEK, a 128-bit tag, and AAD binding stable context.
4. **Wrap the DEK with the KEK**: ideally delegated to KMS/HSM or a standardized wrapping primitive. If using AES-GCM as the wrapping operation, generate a **new nonce unique under that KEK** and include required binding attributes in AAD.
5. **Attach metadata**: versioned key ID, algorithm, nonces/tags, schema version, and context info. Store results consistently with the object and enforce size limits before/after encryption.
6. **Commit only a complete record** (data ciphertext and wrapped DEK together). Never publish an object missing tags or key metadata; if spanning multiple services, use commit/rollback protocols to prevent inconsistent state.
7. **Minimize plaintext DEK lifetime** in memory, logs, crash dumps, and traces. Zeroing `byte[]` in Java is best effort; JIT, garbage collection, and providers can retain copies outside full application control.

### One KEK Can Wrap Many DEKs

This is what a KEK is designed for, yet the **KEK is a concentration of authority**. Every wrap must use a secure scheme and obey nonce/usage limits. When protecting multiple tenants, partition key policies or KEKs by tenant/risk tier. Separating keys by tenant/object still does not replace verifying data access permissions before calling unwrap.

### Data AAD and Wrap AAD Must Have Clear Purposes

Two independent AADs can be used:

```text
dataAAD = Encode("DATA-v1", tenantId, objectId, dataSchemaVersion)
wrapAAD = Encode("WRAP-v1", tenantId, objectId, kekId, wrappingVersion)
```

`Encode` must be an **unambiguous** serialization (length-prefixed, canonical schema, typed fields in fixed order). Never naively concatenate `("ab" || "c")` and `("a" || "bc")` where two distinct metadata sets yield identical bytes. AAD is **not encrypted**, so never put secrets in AAD expecting them to be hidden. Yet changing AAD makes GCM tag verification fail.

A key rotation detail: if rotating only the KEK, **dataAAD should not depend directly on `kekId`** in a model where you want data ciphertext/tag to remain untouched. When rotating the KEK, keep the data context unchanged so **dataNonce + dataCiphertextAndTag** stays intact; only produce a **new wrapped DEK** whose `wrapAAD` carries the new key ID. If policy requires changing `dataAAD` as well, you will have to decrypt and re-encrypt the data/tag (or use another protocol mechanism with equivalent authentication).

## 5. Decryption Flow: Two-Layer Authentication

When reading an object:

1. Validate **version, format, size limits**, and mandatory fields. Determine expected tenant/object ID from the authenticated request or trusted storage path; never take all verification inputs solely from an attacker-controlled payload.
2. Look up `kekId` in the **trusted registry/KMS** for the determined tenant/purpose. Check unwrap permissions; a key ID is not a secret/password.
3. Use the matching KEK to **unwrap the wrapped DEK**, verifying the tag/wrapping integrity and wrap AAD. **Never use the DEK** unless unwrapping succeeded authentication.
4. Check that the unwrapped DEK bytes have the **expected type/length**; temporarily construct a `SecretKeySpec` (if raw bytes live in-process) or use a provider handle.
5. Decrypt `dataCiphertextAndTag` using the DEK, nonce, tag, and matching data AAD. Treat plaintext as valid **only after `Cipher.doFinal` succeeds and the tag is verified**.
6. Enforce **object/resource/action-level** authorization and business constraints; never return sensitive plaintext merely because someone could fetch the wrapped DEK.
7. Never log DEKs, KEKs, plaintext, or excessive operational details; clear temporary secrets as far as practical.

If a wrapped DEK is swapped from another object, wrap AAD binding `tenantId/objectId/purpose` catches the mismatch. If an attacker can also alter unauthenticated metadata and the system blindly trusts it, AAD can be fed the wrong context; therefore maintain a **trusted server-side source of expected context**, not merely “self-describing data” from the client.

**Two tags protect two different things** when GCM is used at both layers: the wrap tag authenticates the wrapped DEK/wrap metadata; the data tag authenticates the payload ciphertext/data metadata. Verifying one tag and skipping the other is a bug.

## 6. Java 17 — Complete Program: Envelope Encryption and KEK Rewrap

The code below deliberately avoids external KMS SDKs outside the JDK. It generates **three in-memory KEKs** (old, new, wrong) via `KeyGenerator`, creates **a 32-byte DEK** via `SecureRandom`, encrypts the content using AES-GCM with the DEK, and then **encrypts/wraps the DEK under another KEK** also using AES-GCM. Using GCM to protect the DEK in this example illustrates **authenticated key encryption**; real KMS/HSM systems or protocols may use **AES Key Wrap** or another wrapping primitive with different APIs and metadata.

Each `seal` call generates a fresh 12-byte random nonce and uses a 128-bit tag. With long-lived KEKs and high operation counts, never rely solely on “random rarely collides”: enforce **strict non-reuse of nonces under the same KEK** and usage limits per GCM policy/design. The demo code uses two independent AAD domains `DATA-v1` and `WRAP-v1` along with `objectId`; metadata is length-prefixed to avoid ambiguous boundaries.

The program intentionally includes these tests:

- Opening a valid envelope with the old KEK: **passes**.
- Using the **wrong KEK**, changing the object ID, modifying data ciphertext/tag, modifying wrapped DEK/tag, or truncating wrapped DEK tag bytes: **rejected**.
- **Rewrapping the DEK** to the new KEK: data nonce and data ciphertext/tag **stay unchanged**; the new KEK decrypts, while the old KEK is no longer accepted for the updated envelope.

Create the exact file **`EnvelopeEncryptionDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class EnvelopeEncryptionDemo {
    private static final int DEK_BYTES = 32;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final SecureRandom RANDOM = new SecureRandom();

    private record Sealed(byte[] nonce, byte[] ciphertextAndTag) {
        Sealed {
            nonce = nonce.clone();
            ciphertextAndTag = ciphertextAndTag.clone();
        }
        @Override public byte[] nonce() { return nonce.clone(); }
        @Override public byte[] ciphertextAndTag() {
            return ciphertextAndTag.clone();
        }
    }

    private record Envelope(String keyId, Sealed wrappedDek, Sealed data) {}

    public static void main(String[] args) throws Exception {
        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(256);
        SecretKey oldKek = keyGenerator.generateKey();
        SecretKey newKek = keyGenerator.generateKey();
        SecretKey wrongKek = keyGenerator.generateKey();

        String objectId = "invoice-42";
        String oldId = "kek-v1";
        String newId = "kek-v2";
        byte[] plaintext = "amount=250;currency=USD"
                .getBytes(StandardCharsets.UTF_8);

        Envelope before = encryptEnvelope(oldKek, oldId, objectId, plaintext);
        System.out.println("Original round-trip: " + Arrays.equals(
                plaintext, decryptEnvelope(before, oldKek, oldId, objectId)));
        System.out.println("Wrong KEK rejected: " + rejects(
                () -> decryptEnvelope(before, wrongKek, oldId, objectId)));
        System.out.println("Wrong object ID rejected: " + rejects(
                () -> decryptEnvelope(before, oldKek, oldId, "invoice-43")));

        byte[] changedData = before.data().ciphertextAndTag();
        changedData[0] ^= 1;
        Envelope forgedData = new Envelope(oldId, before.wrappedDek(),
                new Sealed(before.data().nonce(), changedData));
        System.out.println("Changed data rejected: " + rejects(
                () -> decryptEnvelope(forgedData, oldKek, oldId, objectId)));

        byte[] changedWrap = before.wrappedDek().ciphertextAndTag();
        changedWrap[changedWrap.length - 1] ^= 1;
        Envelope forgedWrap = new Envelope(oldId,
                new Sealed(before.wrappedDek().nonce(), changedWrap),
                before.data());
        System.out.println("Changed DEK wrap rejected: " + rejects(
                () -> decryptEnvelope(forgedWrap, oldKek, oldId, objectId)));

        Envelope tooShort = new Envelope(oldId,
                new Sealed(before.wrappedDek().nonce(), new byte[TAG_BYTES - 1]),
                before.data());
        System.out.println("Short wrapped DEK rejected: " + rejects(
                () -> decryptEnvelope(tooShort, oldKek, oldId, objectId)));

        Envelope after = rewrap(before, oldKek, oldId, newKek, newId, objectId);
        System.out.println("Rewrap keeps data bytes: "
                + Arrays.equals(before.data().nonce(), after.data().nonce())
                + " / " + Arrays.equals(before.data().ciphertextAndTag(),
                        after.data().ciphertextAndTag()));
        System.out.println("New KEK decrypts: " + Arrays.equals(
                plaintext, decryptEnvelope(after, newKek, newId, objectId)));
        System.out.println("Old KEK rejected after rewrap: " + rejects(
                () -> decryptEnvelope(after, oldKek, newId, objectId)));
    }

    private static Envelope encryptEnvelope(
            SecretKey kek, String kekId, String objectId, byte[] plaintext)
            throws GeneralSecurityException {
        byte[] dek = new byte[DEK_BYTES];
        RANDOM.nextBytes(dek);
        try {
            Sealed data = seal(new SecretKeySpec(dek, "AES"), plaintext,
                    associatedData("DATA-v1", objectId, ""));
            Sealed wrapped = seal(kek, dek,
                    associatedData("WRAP-v1", objectId, kekId));
            return new Envelope(kekId, wrapped, data);
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }

    private static byte[] decryptEnvelope(
            Envelope envelope, SecretKey kek, String expectedKekId,
            String objectId) throws GeneralSecurityException {
        if (!envelope.keyId().equals(expectedKekId)) {
            throw new IllegalArgumentException("Unexpected KEK identifier");
        }
        byte[] dek = open(kek, envelope.wrappedDek(),
                associatedData("WRAP-v1", objectId, expectedKekId));
        try {
            if (dek.length != DEK_BYTES) {
                throw new GeneralSecurityException("Unexpected DEK length");
            }
            return open(new SecretKeySpec(dek, "AES"), envelope.data(),
                    associatedData("DATA-v1", objectId, ""));
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }

    private static Envelope rewrap(
            Envelope original, SecretKey oldKek, String oldId,
            SecretKey newKek, String newId, String objectId)
            throws GeneralSecurityException {
        if (!original.keyId().equals(oldId)) {
            throw new IllegalArgumentException("Unexpected old KEK identifier");
        }
        byte[] dek = open(oldKek, original.wrappedDek(),
                associatedData("WRAP-v1", objectId, oldId));
        try {
            if (dek.length != DEK_BYTES) {
                throw new GeneralSecurityException("Unexpected DEK length");
            }
            Sealed wrapped = seal(newKek, dek,
                    associatedData("WRAP-v1", objectId, newId));
            return new Envelope(newId, wrapped, original.data());
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }

    private static Sealed seal(SecretKey key, byte[] input, byte[] aad)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return new Sealed(nonce, cipher.doFinal(input));
    }

    private static byte[] open(SecretKey key, Sealed sealed, byte[] aad)
            throws GeneralSecurityException {
        byte[] nonce = sealed.nonce();
        byte[] ciphertextAndTag = sealed.ciphertextAndTag();
        if (nonce.length != NONCE_BYTES || ciphertextAndTag.length < TAG_BYTES) {
            throw new IllegalArgumentException("Invalid sealed field");
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag);
    }

    private static byte[] associatedData(
            String domain, String objectId, String kekId) {
        byte[] d = domain.getBytes(StandardCharsets.UTF_8);
        byte[] o = objectId.getBytes(StandardCharsets.UTF_8);
        byte[] k = kekId.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(12 + d.length + o.length + k.length)
                .putInt(d.length).put(d)
                .putInt(o.length).put(o)
                .putInt(k.length).put(k)
                .array();
    }

    @FunctionalInterface
    private interface Operation { void run() throws GeneralSecurityException; }

    private static boolean rejects(Operation operation) {
        try {
            operation.run();
            return false;
        } catch (GeneralSecurityException | IllegalArgumentException e) {
            return true;
        }
    }
}
```

Compile and run on JDK 17+ supporting AES-256-GCM:

```bash
javac --release 17 EnvelopeEncryptionDemo.java
java EnvelopeEncryptionDemo
```

**Stdout** (compiled and verified on Java 17):

```text
Original round-trip: true
Wrong KEK rejected: true
Wrong object ID rejected: true
Changed data rejected: true
Changed DEK wrap rejected: true
Short wrapped DEK rejected: true
Rewrap keeps data bytes: true / true
New KEK decrypts: true
Old KEK rejected after rewrap: true
```

The program uses random keys and nonces and **never prints key material**, so ciphertext bytes differ on every run, yet the 9 boolean lines above reflect the expected behavior. If Java or the provider does not support the transformation or key size under current policy, `getInstance`/`init` will throw an error; never silently downgrade key length or cipher mode just to “make it run.”

### Why Does This Demo Properly Illustrate the Principle?

- `encryptEnvelope` generates a **separate DEK** and uses it to encrypt **plaintext data**; `kek` only wraps the **DEK** and never directly encrypts the content.
- `Sealed` stores the nonce and `ciphertextAndTag`; byte arrays are cloned when constructing/returning the record so input-tampering tests **never silently mutate the original envelope**.
- `associatedData` encodes domain, object ID, and key ID in UTF-8 with **three big-endian `int` length prefixes**. Each field tuple has unambiguous boundaries; this illustrates internal encoding, not a public interoperability standard.
- `DATA-v1` and `WRAP-v1` provide domain separation: sharing a “context” concept does not mean both layers carry identical AAD bytes. `kekId` is bound only in wrap AAD so rewrapping leaves data ciphertext unchanged.
- `decryptEnvelope` rejects if the envelope's key ID does not equal the **expectedKekId** chosen by the caller. In production, the expected ID must come **from a trusted tenant/key registry**, never “trusted” by copying `envelope.keyId()` into the expected argument.
- When `Cipher.doFinal` fails GCM tag verification, Java typically throws `AEADBadTagException` (a subclass of `BadPaddingException`). The `rejects` helper groups errors purely for display; real APIs must classify errors internally and return public errors that avoid creating an oracle.
- `rewrap` must decrypt the **DEK**, yet **never calls `open` on the data ciphertext**. Consequently, data nonce and data ciphertext/tag remain identical, verified via `Arrays.equals`.
- `Arrays.fill(dek, (byte) 0)` attempts to clear the temporary `byte[]`, **without guaranteeing** every copy in the JVM/hardware is gone; in production, prefer KMS/HSM with non-exportable KEKs and strict heap/secret lifecycle management.

### Example Limitations to Recognize

The standalone program processes **one object and one KEK transition**. It does not persist envelopes to disk/database, check IAM, provide transaction/rotation locks, serialize the full structure defensively against untrusted inputs, or perform key discovery or KMS calls. `Operation`/`rejects` helps demonstrate rejection cases and should not be copied directly as an API contract.

In particular, `Sealed` in the demo uses AES-GCM for **both data and wrapping**. In real KMS/HSM setups, dedicated wrapping mechanisms such as AES Key Wrap or KMS operations like `Encrypt`/`Decrypt`/`GenerateDataKey`/`ReEncrypt` are used depending on the provider. **Never** manually reinterpret GCM-wrapped output as AESWrap output: the algorithms, IVs, tags, and formats are **different**.

## 7. Rewrap, Re-Encrypt, and Rotate: Three Distinct Actions

The phrase “key rotation” is easily misunderstood because multiple layers exist:

### 7.1 Rewrap (Change KEK, Keep DEK)

```text
BEFORE:
plaintext data -- encrypt(DEK1) --> ciphertextData1
DEK1           -- wrap(KEK-A) --> wrappedDEK-A

AFTER REWRAP:
ciphertextData1             [UNCHANGED]
DEK1           -- wrap(KEK-B) --> wrappedDEK-B
keyId: KEK-A -> KEK-B
```

This process requires **unwrap permission on KEK-A** and **wrap permission on KEK-B**. Depending on the KMS, the operation may execute entirely inside the key service without returning the DEK to the app, or require unwrapping the DEK inside a trusted boundary to rewrap it.

**Advantage:** avoids reading and re-encrypting a 10 GiB data file; only a short DEK and metadata are processed. Cost scales with the number of objects/DEKs to migrate, KMS calls, and metadata writes. With 1 million objects, you still rewrap roughly 1 million wrapped DEKs if each object has its own DEK: **it is not an O(1) operation across the whole store**.

**Operational requirement:** write the new wrapped DEK + key ID + related metadata **atomically** or via a recoverable workflow. Never delete KEK-A before all required objects/backups have migrated and recovery procedures confirm KEK-B works.

### 7.2 Rotate DEK (Replace Data Encryption Key)

If the DEK itself was compromised or reached its usage limit, generate a **new DEK2**, decrypt data with DEK1, **re-encrypt** with DEK2 using a proper nonce/AAD, and store the new ciphertext/tag. Then wrap DEK2 under an approved KEK.

```text
dataCiphertext1 -- decrypt(DEK1) --> plaintext
plaintext       -- encrypt(DEK2) --> dataCiphertext2
DEK2            -- wrap(KEK-B)  --> wrappedDEK2
```

This touches the full dataset and requires careful handling of **temporary plaintext**, storage, timeouts, consistency, checksums/integrity, and rollback.

**Do not equate rewrap with DEK rotation.** If DEK1 was compromised, merely rewrapping it under a new KEK **does not make DEK1 secret again**.

### 7.3 KMS-Managed Rotation (Replacing Key Material Inside the Service)

Some KMS offerings provide **automatic rotation** for managed keys, keeping older key material versions to decrypt historical ciphertexts while applying the new version to new encryptions. Depending on provider and key type, **automatic rotation does not mean every old wrapped DEK is immediately rewrapped**, nor does every object's key ID change.

Read your provider's exact semantics: alias changes, key versions, which key metadata ciphertexts carry, decrypt rights for old versions, propagation delays, backup/migration behavior, and API limits. **Never assume** flipping a “rotation” toggle erases the impact of previously exposed key material.

### 7.4 Key Compromise Incidents and Legacy Copies

| Event | Typical Actions Required | Why Rewrap Alone Is Insufficient in Some Cases |
| --- | --- | --- |
| Migrating custody from KEK-A to KEK-B, no leak suspected | Rewrap DEKs + update policy, test backup/restore | This is the exact efficient use case for rewrap |
| A service's permissions are revoked | Narrow KMS permissions + credential rotation + audit + evaluate plaintext/DEK caches | The service may have extracted DEKs or data while authorized |
| **KEK-A compromised** | Incident response, block KEK-A, audit old ciphertexts/wrapped DEKs and backups, rewrap and potentially re-encrypt data | Anyone holding copies of **wrappedDEK-A + ciphertextData** and KEK-A can still decrypt old copies; rewrapping live records **does not recall snapshots** |
| **DEK compromised** | Re-encrypt affected data with a new DEK, rewrap, retire old copy per procedure | A new KEK does not alter the fact that the attacker knows the old DEK |
| Data deletion (“crypto-erasure”) | Procedures to destroy related keys, backups/caches/snapshots, retention controls | Deleting one wrapped DEK does not guarantee no copies or plaintext survive elsewhere |

**Historical confidentiality cannot be restored retroactively by rotation.** Once a key has been compromised, assess what data the attacker **already captured**, along with backups, snapshots, logs, and cached DEKs/KEKs, rather than looking only at the current key.

## 8. KMS/HSM in the Envelope Encryption Model

### 8.1 What Do Key Services Typically Do?

An API such as `GenerateDataKey` may return:

- A **plaintext DEK** so the application can encrypt data locally (if API/policy allows).
- An **encrypted/wrapped DEK** to persist alongside the encrypted object.
- Required metadata such as KMS key ID and encryption context, depending on the service.

After encrypting data, the application discards the plaintext DEK. For later decryption, it sends the **wrapped DEK** plus matching **encryption context**/metadata to KMS under its granted permissions; KMS checks policy and returns the plaintext DEK or unwraps within the protected boundary. Exact API names, response fields, and semantics vary by vendor.

Some HSMs/KMS systems keep KEKs **non-exportable**, restricting them to wrap/unwrap/re-encrypt. Even so, if an API returns a plaintext DEK, the application must still protect that DEK while it lives in process memory. **“Non-exportable KEK” does not mean plaintext DEK never entered the JVM**.

### 8.2 Policy and Auditing Matter as Much as Algorithms

- Only authorized services, within the right tenant/project and context, may call **wrap/unwrap**.
- Separate **encrypt-only** roles (allowed only to wrap/create new data) from **decrypt-capable** roles when the use case permits.
- Protect key policies, aliases/registries, IAM, service identities, network boundaries, quotas, and key deletion schedules.
- Audit **key ID, caller identity, purpose, valid object/tenant reference, timestamp, and outcome**. Never log plaintext DEKs, KEKs, plaintext data, or request secrets.
- Encryption context APIs generally treat context as **non-secret AAD**: never put passwords, tokens, or sensitive PII there if KMS logs/APIs can expose context.
- Test permission denials and provider outages before rollout. Never fall back to weak hard-coded/local keys just to “stay up.”

### 8.3 Comparing Ways to Protect a DEK

| DEK Protection Method | Model | Notes |
| --- | --- | --- |
| **AES-GCM with KEK** | Encrypts DEK into ciphertext + tag; needs unique nonce per KEK | Implementable via JCA; must serialize nonce/tag and bind AAD; used in this lesson's demo |
| **AES Key Wrap (RFC 3394)** | Primitive dedicated to wrapping key material | Scheme-level integrity check; different input format/length rules from GCM; `Cipher` names/support vary by provider |
| **AES Key Wrap with Padding (RFC 5649)** | Wrap variant supporting more general key material lengths | Do not confuse with PKCS5Padding/GCM; verify provider support |
| **KMS/HSM wrap/unwrap** | KEK managed by service/hardware; app calls authorized APIs | Involves KMS key IDs, encryption context, IAM, logging, latency, and quotas; never assume all providers share internal algorithms |
| **RSA-OAEP protecting DEK** | Public key encrypts short DEK; private key decrypts | Use when asymmetric custody is required, with proper OAEP params/key custody; avoid raw RSA or legacy RSA PKCS#1 v1.5 for new designs |
| **Direct data encryption via KMS** | Some services encrypt small inputs directly | For large data, use local DEKs and let KMS handle keys only; check specific input size limits |

**Never** use raw `AES/ECB/NoPadding` to “encrypt a DEK,” XOR with a constant string, hash a DEK as a “wrapped key,” or treat Base64/hex as encryption. A key-wrapping primitive must provide confidentiality and scheme-level integrity.

## 9. Principles for Nonces, AAD, and Algorithms

### 9.1 Both Encrypted Data and Wrapped DEKs Need Integrity

If a wrapping algorithm provides confidentiality without integrity, a corrupted or tampered DEK may enter decryption or trigger hard-to-diagnose failures. Use AEAD or a key-wrap scheme with integrity checks so altered key material is never accepted.

For `AES/GCM/NoPadding`:

- GCM tags are typically **128 bits**; Java accepts `GCMParameterSpec(128, nonce)` with **length in bits**.
- A **12-byte** nonce is standard; it must be unique **under the same key**. Data encryption uses the **DEK**, while wrapping uses the **KEK**, creating two separate nonce-management scopes.
- `Cipher.updateAAD(...)` must run before `update`/`doFinal` on data in Java GCM; decryption must supply the **exact same AAD bytes**.
- `Cipher.doFinal(...)` releases valid plaintext only when tag verification succeeds. Never publish intermediate output prior to authentication.
- If the tag, nonce, AAD, or key is modified, GCM decryption fails (`AEADBadTagException` is common). **You cannot reliably distinguish the exact root cause solely from the exception type**.

With 96-bit random nonces and a long-lived KEK, limit wrapping counts so nonce collision probability remains within acceptable risk, or use a policy-enforced unique nonce allocator. **Never reuse a nonce under the same KEK** merely because the two DEKs differ.

### 9.2 Binding Tenant, Object, and Role

A dangerous mistake is taking tenant A's wrapped DEK, pairing it with tenant B's ciphertext, and **expecting the data tag alone to solve everything**. The data tag may fail if the key differs, yet that alone does not establish a sound authorization model.

Defense-in-depth layers should include:

1. **Access control:** only fetch objects and call unwrap for the authorized tenant.
2. **Trusted key ID mapping:** `tenantId + purpose + kekId` maps to the authorized KEK.
3. **Wrap AAD:** binds the wrapped DEK to object/tenant/purpose and version.
4. **Data AAD:** binds ciphertext to object/tenant/purpose and format/version.
5. **Authenticated data format:** guarantees both writer and reader agree on metadata representation before computing tags.

AAD does not keep metadata confidential; add encryption if metadata fields themselves must be hidden. Never omit AAD simply because “the ciphertext already has a tag.”

### 9.3 Do Not Put `kekId` in Data AAD If Data Must Stay Intact During Rewrap

In the demo, `associatedData("DATA-v1", objectId, "")` omits `kekId`, while `associatedData("WRAP-v1", objectId, kekId)` includes it. Thus after rewrap:

```text
dataNonce:              unchanged
dataCiphertextAndTag:   unchanged
wrappedDEK:             changed
wrapNonce:              changed
kekId:                  changed
```

This is not “skipping key ID authentication”: `kekId` is still **validated in the trusted key mapping** and **authenticated by wrap AAD**. Separating metadata by layer lets both integrity and key rotation work coherently.

## 10. Storage and Consistent Transactions When Rewrapping Millions of Objects

An object store may need to migrate from KEK version 1 to 2 while serving live traffic. The hard parts are usually **consistency**, not `Cipher`:

1. **Read an object snapshot/version:** fetch data ciphertext/tag, wrapped DEK, key ID, context, and version metadata from one consistent revision.
2. **Authorize old unwrap and new wrap:** never migrate all objects blindly if one tenant lacks permissions/conditions. Enforce throughput/KMS quota limits.
3. **Rewrap and verify:** call the provider/KMS with the right key IDs; test decrypting at least a sample under the new KEK per policy. For each object, if unwrap/authentication fails, **never overwrite the old wrapped DEK**.
4. **Atomic compare-and-swap:** update `(keyId, wrappedDEK, wrapMetadata, envelopeVersion)` only if the object was not concurrently modified or matches the same ETag/version. On concurrent modification, re-read and run bounded retries rather than clobbering newer data.
5. **Ensure recoverability:** maintain migration state machines, idempotent retries, checksum/record count checks, key-free logging, and enough state to resume if the job aborts mid-run.
6. **Temporarily support reading both KEKs:** during rollout, the service must resolve the matching key ID for both old and new versions; retire old unwrap permissions only after zero dependencies remain.
7. **Backups and restores:** snapshots hold versioned key IDs/wrapped DEKs; before destroying an old KEK, account for older backups so restoration isn't broken. Never assume rewrapping live objects automatically updates replicas/backups.
8. **Verify stop conditions:** reconcile inventory and audit logs, monitor read error rates and exceptions by key version, and execute planned cutover/disablement of the old key.

**Bad example:** writing `kekId="v2"` first while leaving `wrappedDEK` from v1; readers then pick KEK-v2 and unwrap fails. Another bad example: wrapping the DEK with v2 but persisting the object without the new tag or wrap nonce. **Related fields must update atomically together**.

## 11. Exception Handling and Error Classification

| Symptom | Possible Cause | Proper Handling |
| --- | --- | --- |
| `AEADBadTagException` when unwrapping DEK with AES-GCM | Wrong KEK, mismatched wrap AAD, modified or truncated wrap nonce/tag/ciphertext | Reject DEK; never try fixing tags or guessing keys; inspect metadata and internal source bytes |
| `AEADBadTagException` when decrypting data | Wrong DEK, mismatched data AAD/nonce, corrupted data ciphertext/tag | Release zero plaintext; verify object consistency, context, and storage transport |
| `IllegalArgumentException` due to too-short nonce/tag | Missing minimum layout bytes, invalid metadata | Reject in parser before allocating large buffers or calling provider |
| `InvalidKeyException` on `Cipher.init` | Invalid key, wrong type, rejected by provider/key policy | Check key type/size and policy; no weak fallback |
| KMS returns access denied | IAM/key policy forbids unwrap | Reject and audit; **never log DEK** or fall back to a default local KEK |
| KMS rate limit/timeout | Quota or network issue; unrelated to ciphertext integrity | Retry with backoff/jitter, deadlines, and caps; avoid mis-decrypting or leaking secrets |
| `kekId` missing from registry | Corrupted metadata, revoked key, or sender unauthorized for that key | Never load keys outside allowlist; return standardized error |
| Rewrap succeeded yet reading with new KEK fails | Mismatched wrap AAD, key ID, serialization, or non-atomic update | Halt rollout, inspect by record version, execute controlled rollback |
| Decryption succeeds yet object belongs to wrong tenant | Missing authorization/context binding; logic bug | Enforce data permissions, tenant ID in AAD, and trusted resource mapping |
| Deleted old KEK, then backup restore fails | Older copies still depend on the deleted KEK | Drill restores before key deletion; manage retention per version |

**Errors from the wrapping layer and data layer should not be conflated in internal monitoring**, yet external responses must not expose key material details or authentication state that aids an attacker. Never return partial decrypted data before tag verification; never iterate over lists of key IDs/nonces/tags hoping one “unlocks” it.

## 12. Common Design Questions

### 12.1 Must Every Record Have Its Own DEK?

Not strictly. One DEK can cover multiple records if the protocol enforces nonce management, usage limits, and full threat modeling. However, **a separate DEK per object/small group** limits blast radius on DEK compromise and simplifies lifecycle access control, deletion, and re-encryption. The trade-off is more wrapped DEKs, metadata, and KMS calls. Choose granularity based on payload size, object count, access frequency, and manageability.

### 12.2 Should Plaintext DEKs Be Cached to Reduce Latency?

Caching cuts KMS calls yet **extends plaintext DEK lifetime and exposure surface**. If needed, enforce TTLs, entry caps, tenant isolation, process permissions, lifecycle eviction, restricted debugging/heap dumps, auditing, and replay/stale-policy risk assessment. **Caching encrypted DEKs** lacks the same plaintext exposure risk, though cached metadata must still stay consistent during rotation.

### 12.3 Can a Shared Passphrase Be Used as a KEK?

Never treat a guessable configuration string like `"master-password-123"` as a KEK. A KEK requires proper entropy, key management, and policy. If the model genuinely starts from a **user password**, use a password-based KDF (such as Argon2id/scrypt/PBKDF2 per architecture and environment) with salt, work factor, and proper design—never simply call `password.getBytes()` as an AES key. That model differs from a randomly generated KMS-backed KEK.

### 12.4 Can Both KEK and DEK Be AES-256?

**Yes**—the same AES algorithm, yet **two independent keys with distinct roles**. “Key separation” is more than renaming variables: generate independent key material, separate permissions and functions, protect the KEK more strongly, manage versions, and avoid reusing one key for both data and wrapping. If both hold the same 32 bytes, you have not achieved key separation.

### 12.5 Can a DEK Be Wrapped with a Recipient's Public Key?

Yes—if the design uses **RSA-OAEP** or standardized KEM/HPKE, you can encrypt/wrap a short DEK for the recipient's public key so only the private-key holder can unwrap it. Here the “KEK” is an asymmetric **key-encryption mechanism** rather than a symmetric AES key. Still, you need authentic recipient public keys, valid schemes, proper OAEP/KEM parameters, and private key custody policies; **never use raw RSA or homebrew hybrid protocols**.

### 12.6 Can a “Wrapped DEK” Serve as an Authorization Token?

**No.** A wrapped DEK is ciphertext of key material, not a capability token proving caller rights. The system must still authenticate the user/service, authorize object access, restrict KMS unwrap, and bind tenant/context. Anyone able to read the envelope can typically see the wrapped DEK; that **does not mean** they have KMS permission to unwrap it.

### 12.7 Is Crypto-Erasure Enough to Delete Data?

**Crypto-erasure** permanently destroys the key material needed to decrypt; if each object has its own DEK and no copies of the DEK or unwrap-capable wrapped DEK survive, data can become cryptographically unrecoverable. Yet deleting one database row does not prove completion: audit DEK caches, active KEK versions, snapshots, backups, plaintext copies, logs, and hosts that previously decrypted it. Destroying a shared KEK to erase one object can **accidentally make all other objects undecryptable**.

### 12.8 Does Envelope Encryption Automatically Make Data “End-to-End Encrypted”?

No. If the server handles plaintext DEKs and plaintext data, the server sits inside the trust boundary. End-to-end encryption has a different key-custody and endpoint model; envelope encryption can be a building block, yet does not by itself create E2EE. Specify **who can unwrap, who sees plaintext, and where keys are decrypted**, rather than counting encryption layers.

## 13. Production and Testing Checklist

### Key Security

- [ ] DEKs and KEKs differ in **key material, role, usage permissions, and lifecycle**.
- [ ] Plaintext DEKs live only ephemerally inside controlled boundaries; KEKs reside in KMS/HSM/keystores per policy.
- [ ] Proper CSPRNG, GCM nonces **never reused under the same key**, and usage limits enforced.
- [ ] Trusted key ID registry exists; tenant, object, and purpose/role are bound into authenticated context.
- [ ] Zero DEKs/KEKs/plaintext in logs, traces, metrics, exceptions, or envelope metadata.
- [ ] Protocol avoids ECB, raw RSA, or hashes as key-wrapping primitives.

### Envelope and Integrity

- [ ] Format defines version, algorithm allowlist, key ID, nonces/tags, and canonical byte layout.
- [ ] Data AAD stays stable per object/tenant/purpose; wrap AAD binds key ID/context, enabling independent rewrap when desired.
- [ ] Parser rejects missing headers/tags and enforces length bounds before allocating or calling `Cipher`.
- [ ] Object and wrapped DEK reads/writes stay consistent; zero plaintext exposed before verifying both wrap and data tags.
- [ ] Tests cover flipping 1 bit in ciphertext/tag/nonce, wrong KEK, wrong object ID/tenant/AAD, missing tag, altered key ID, and invalid version.
- [ ] For KMS, test key permissions, key states, quotas/timeouts, key rotation, and policy revocation.

### Rotation and Operations

- [ ] Distinguish **KEK rewrap** from **DEK re-encryption** with separate runbooks.
- [ ] Rewrap atomically updates `wrappedDEK + keyId + wrap metadata` with ETag/concurrency guards.
- [ ] Temporarily support required read key versions; destroy old keys **only after** verifying objects, backups, and restore paths.
- [ ] Migration metrics, audit trails, batch sizing, idempotent retries, and rollback plans are in place.
- [ ] Incident response plan covers KEK/DEK compromise, including historical copies and backups.

## 14. Practice Exercises

1. Draw an envelope diagram for a three-tenant invoice storage system. Would you choose one DEK per invoice or per tenant? At what tier does the KEK sit? Explain the trade-offs in KMS calls and compromise blast radius.
2. Run `EnvelopeEncryptionDemo.java`. Point out where the DEK is generated, used to encrypt data, wrapped, unwrapped, and temporarily cleared. Does the KEK ever encrypt the original `plaintext` directly?
3. Why does the `Wrong object ID rejected` test succeed even though `objectId` is not inside the plaintext? If you take an arbitrary object ID from the payload to build AAD, what identity-binding risk remains?
4. Add `tenantId` to `associatedData` using length prefixes. Write a test that swaps wrapped DEKs between two tenants and prove decryption fails under the wrong context.
5. Contrast `Rewrap keeps data bytes: true / true` with DEK rotation. Why does rewrapping **not alter data ciphertext/tag**, whereas changing the DEK normally requires changing them?
6. Suppose the company exposes KEK-v1 and an attacker captured a snapshot of `wrappedDEK-v1`. Does rewrapping live records to v2 invalidate the old snapshot? Write an incident response plan.
7. Design a database model with `object_version`, `kek_id`, `wrapped_dek`, `wrap_nonce`, `data_nonce`, and `data_ciphertext_and_tag`. Sketch a compare-and-swap update statement for rewrap under concurrent writers.
8. Design KMS test cases: unwrap permission denied, key rotation, key disabled, old backup restore, and KMS unavailable. Specify which cases should retry and which must fail closed.
9. Explain why using the same `AES/GCM/NoPadding` cipher in the demo for two different roles still achieves **key separation**, and why nonces must never be reused under the same KEK.
10. If one object's DEK must be permanently deleted, which copies of plaintext/encrypted keys, backups, caches, and snapshots must be checked before declaring crypto-erasure complete?

## References

- [NIST SP 800-38D — GCM/GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): requirements for authenticated encryption, IV/nonces, and tags.
- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): terminology, key management, lifecycle, and cryptoperiods.
- [RFC 3394 — Advanced Encryption Standard (AES) Key Wrap Algorithm](https://www.rfc-editor.org/rfc/rfc3394): AES key-wrapping method.
- [RFC 5649 — AES Key Wrap with Padding Algorithm](https://www.rfc-editor.org/rfc/rfc5649): padded variant supporting more general key material lengths.
- [Java SE 17 — `Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `AES/GCM/NoPadding`, `updateAAD`, `doFinal`, authentication failures, and `WRAP_MODE`.
- [Java SE 17 — `GCMParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): tag length in bits and IV/nonces.
- [Java SE 17 — `KeyGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html): generating AES keys via providers.
- [Java SE 17 — `SecretKeySpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html): in-memory key byte wrapper; not a substitute for KMS.
- [Java SE 17 — Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): providers, key generation, Cipher/JCE, and service architecture.
