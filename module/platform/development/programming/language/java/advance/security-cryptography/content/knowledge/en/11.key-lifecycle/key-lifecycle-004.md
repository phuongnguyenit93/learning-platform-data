# 11.4 Key Identifiers, Key Versions, and Backward Decryption of Legacy Data

When a Java system encrypts data to store for months or years, the question is not just **“how do we encrypt with AES-GCM?”** but also **“after rotating the key, how do we identify the right old key to read stored ciphertexts?”**. If you only keep a single `CURRENT_KEY` variable and overwrite the key bytes on each deployment, legacy ciphertexts will generally **fail to decrypt** with the new key. Adding a new key copy does not automatically convert existing data.

The solution requires a durable contract consisting of a **key identifier (key ID)**, **key lifecycle/version (key version)**, **ciphertext format version (envelope/format version)**, and a policy for **retaining backward decryption capability**. The system can use a new key for newly generated data while preserving restricted decryption permissions for older records until they are migrated, expired, or destroyed per policy.

Core insight: **a key ID is a reference to a key, not the key itself**; **a version number does not magically reconstruct an old key**; and **decrypting with the right key while skipping integrity or authorization checks is still insecure**. This lesson builds long-term key management reasoning in Java, using AES-GCM as a concrete example with a Java 17+ program verifying rotation, retaining old keys, re-encryption, and handling tampered data.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish `keyId`, `keyVersion`, `formatVersion`, business data schema versions, and encryption algorithms.
2. Design a ciphertext/envelope carrying sufficient metadata to select the right key later: format, key ID, nonce, ciphertext, tag, and authenticated context.
3. Describe **active-for-encryption**, **decrypt-only**, **disabled/revoked**, and **destroyed** states without confusing “no longer used for new encryption” with “no longer allowed to decrypt.”
4. Implement a policy to “encrypt with the current active version, decrypt using the version stamped on the ciphertext” without blindly trying every key.
5. Understand how to use AES-GCM and `updateAAD` to bind header/key ID metadata, releasing plaintext only after tag verification succeeds.
6. Compare rotation without data migration, **lazy migration**, **batch re-encryption**, **DEK/KEK rewrap**, and each approach's limitations.
7. Establish rollout, rollback, backup/restore, auditing, and key revocation procedures without unintended data loss.
8. Write tests for backward readability, data migration, missing keys, swapped key IDs, modified ciphertext/tag, modified AAD, and per-tenant isolation.

## 2. Concepts: Key ID vs. Key Bytes and Key Version

Suppose a service stores documents:

```text
Document A (2025)  -- encrypted with --> key version 1001
Document B (2026)  -- encrypted with --> key version 1002

Key registry:
  1001 -> Key material #1, status DECRYPT_ONLY
  1002 -> Key material #2, status ACTIVE
```

When reading A, the system retrieves `keyId=1001` stored beside or inside the ciphertext, looks up authorized key #1, and authenticates the data. When creating C, the system uses key #2 and records `keyId=1002`. There is no reason to force A to decrypt with key #2 merely because “the active key changed.”

| Term | Meaning | Example | What Must Not Be Inferred |
| --- | --- | --- | --- |
| **Key material** | Actual secret key value, possibly residing in KMS/HSM | 32-byte AES-256 key, key handle | Cannot be recomputed from key ID alone |
| **Key ID** | Identifier to locate the right key or key reference | `document-prod/1002`, opaque UUID, number `1002` | Not a secret; does not by itself prove the key is trusted |
| **Key version** | Generation/version of key material or version within a key resource | `v1`, `v2`, or provider key version | Does not equal ciphertext format version |
| **Active key** | Version selected by policy for **new encryptions** | `1002` | Does not mean all old data already uses key `1002` |
| **Decrypt-only key** | Disallowed for new encryption; still authorized to decrypt valid data within permitted scope | `1001` | Does not mean “deleted key” |
| **Envelope format version** | Version of header/nonce/tag/serialization layout | `formatVersion=1` | Not key age or key version |
| **Algorithm/profile** | Permitted algorithm and parameters | `AES/GCM/NoPadding`, 12-byte nonce, 128-bit tag | Never let requests pick a weaker algorithm |
| **Data/schema version** | How business plaintext is interpreted | `documentSchema=4` | Not directly tied to key rotation |
| **KEK / DEK** | Key-encryption key and data-encryption key in envelope encryption | KEK in KMS, per-object DEK | Rewrap does not apply automatically if one key encrypts data directly |

A `keyId` name may already embed the version, or a system may store `keyAlias` + `keyVersion` as two fields. **Splitting into two fields is not mandatory**, yet you need an **unambiguous, immutable reference to the key material version**. If an alias `"current"` moves to a new version, legacy ciphertexts cannot store only a mutable alias without a version.

### Avoid Colliding Three Kinds of “v1”

For example, a record containing:

```json
{
  "envelopeVersion": 2,
  "keyId": "documents/production",
  "keyVersion": "7",
  "documentSchemaVersion": 4
}
```

This is **descriptive metadata JSON**, not the binary format of the program in Section 7. `envelopeVersion=2` indicates how to parse the package; `keyVersion=7` is the key generation; `documentSchemaVersion=4` governs plaintext deserialization. These three versions can evolve **independently**. Never use one ambiguous `version` field for all three without clearly defining its meaning.

### Does a Key ID Need to Be Secret?

Usually **no**. A key ID is an identifier or reference that can appear in a ciphertext header. However, predictable names can still reveal system/tenant names; use opaque identifiers when limiting metadata leakage matters. Even though public, **never put raw key bytes, passwords, or secret tokens in the header**.

An ID parsed from an unauthenticated ciphertext is strictly **input-supplied data**. It may act as a routing hint to an allowlisted key, never as an authorization decision: an attacker must never gain permission to decrypt another tenant's key simply by altering the header.

## 3. Key Lifecycle Model and Operation Permissions

A long-term storage system usually separates **new encryption** permission from **legacy decryption** permission. Illustrative state table:

| State | Encrypt New Data | Decrypt Legacy Data | Operational Decision |
| --- | --- | --- | --- |
| `PENDING` / `STAGED` | No | Usually no | Distribute key, configure, and test before activation |
| `ACTIVE` | **Yes** | **Yes** | Current key; enforce nonce uniqueness and usage limits |
| `DECRYPT_ONLY` | **No** | **Yes**, conditionally | Allow reading legacy ciphertexts during retention/migration |
| `SUSPENDED` / `DISABLED` | No | No while disabled | Temporarily lock or revoke access per policy |
| `RETIRED` / `DESTROYED` | No | No; lost keys may be unrecoverable | Only after confirming dependent data no longer needs reading, or migration finished |

State names in the table are **example application policies**, not mandatory names in Java APIs or every KMS. Each provider may define different states and rotation modes. In particular, **`DECRYPT_ONLY` must be enforced by real permissions/logic**, not just by updating a status column while every service keeps calling encrypt with the old key.

Normal rotation flow:

```text
Phase 1:
   v1 ACTIVE -> both encrypt and decrypt

Phase 2:
   v1 DECRYPT_ONLY
   v2 ACTIVE -> all new ciphertexts stamp keyVersion=v2

Phase 3 (if needed):
   decrypt + authenticate v1 record
   re-encrypt with v2 and a fresh nonce
   commit v2 record safely

Phase 4:
   audit all live objects, backups, snapshots, jobs, DR copies per policy
   -> may disable/destroy v1 once zero dependencies remain and retention allows
```

A **suspected key compromise** differs from planned rotation. Keeping the old key around for decryption may pose ongoing risk if the attacker also holds it. Prioritize containment, blocking unauthorized access, assessing exposed data, emergency re-encryption, rotating dependencies, and following incident response procedures. **Re-encrypting now cannot recall plaintext the attacker already read in the past**.

## 4. Why Ciphertext Must Carry an Immutable Key Reference

Common failure example:

```text
2025: encrypt(payload, System.getenv("APP_ENCRYPTION_KEY")) -> store nonce+ciphertext+tag
2026: replace APP_ENCRYPTION_KEY with another value, without storing key ID/version
2027: call decrypt on 2025 record with new key -> tag verification fails
```

In AES-GCM, decrypting with the wrong key typically fails during tag verification; the application cannot guess the old key from the ciphertext. If the old key no longer exists in any valid vault or backup, **data can be permanently lost**.

Proper model:

```text
record = {
  formatVersion,
  immutableKeyReference,  <-- exact version of key material
  nonce,
  ciphertext,
  authenticationTag
}

decrypt(record):
   parse+validate formatVersion
   resolve key via trusted key registry and authorization
   verify AEAD with nonce, ciphertext, tag, and AAD
   only then interpret plaintext
```

**Never store an ambiguous key reference** such as `keyId="current"` if that name will point to different key bytes after rotation. If a provider uses forwarding aliases, store the **specific version** or sufficient cryptographic service metadata so the provider resolves the exact historical version without relying on the current alias. Some KMS services track versions inside an internal ciphertext blob; do not assume that is universal—check the API contract.

### What Must a Key Registry Guarantee?

A proper key registry/store should answer:

- Which **environment** (prod/staging), tenant/trust domain, application, and purpose does this `keyRef` belong to?
- Which algorithm does it use, does it still hold **decrypt permission**, and is the key material still available?
- Is it an **immutable reference** to the required key generation?
- Is the caller authenticated and authorized for this **specific record**?
- If the key is disabled/destroyed/expired, how does the system fail closed and report/log it?
- During key rotation, can we audit each record's key version and count records still depending on the old key?

A key ID is strictly a **lookup key**. **Never** allow requests to specify a secret file path or arbitrary key URI and use it directly. The key registry must enforce allowlists and server-side authorization to prevent cross-tenant decryption and key-enumeration abuse.

## 5. Packaging Key ID and Version in an Authenticated Envelope

For clarity, this lesson uses a **demo v1** binary envelope for AES-256-GCM:

```text
offset   length   field                      meaning
0        4        magic "KVR1"               format marker
4        1        formatVersion = 1          envelope version
5        4        keyId (int32 big-endian)   1001 or 1002 in the example
9        12       nonce                      GCM IV/nonce, freshly generated each time
21       N        ciphertext                 ciphertext of N plaintext bytes
21+N     16       authentication tag         GCM tag, 128 bits

header = magic || formatVersion || keyId || nonce
envelope = header || ciphertext || tag
```

Each record uses a fresh 12-byte nonce and a 16-byte tag. Java's `ByteBuffer` defaults to **big-endian**, and any specification must fix byte order. This is a **lesson-defined format**, not a standard automatically interoperable with external services. Do not copy it verbatim into production without a security review, KMS integration, nonce allocation policy, size limits, and a migration path.

Crucially, **the header must be authenticated**. The encryptor feeds the exact header bytes into AES-GCM **AAD**. The decryptor feeds the exact same header bytes. If anyone alters `keyId=1001` to `1002` without the key and ability to forge a valid tag, GCM verification must fail. Even if two IDs happened to point to the same key material, changing AAD-bound header bytes makes tag verification fail.

Example v1 profile:

```text
AAD = fixedDomain || headerBytes || uint32be(contextBytes.length) || contextBytes

fixedDomain = ASCII "document-envelope:v1"
contextBytes = application-verified and consistently serialized context
```

`fixedDomain` provides domain separation across uses. `headerBytes` binds the format, key ID, and nonce. `contextBytes` can bind document/tenant identity to the ciphertext. **AAD data is not encrypted**, yet it is authenticated when the tag verifies; the decryptor must supply the exact same bytes.

The demo uses a fixed context string `tenant-7/document-42` as an opaque identifier. With multiple user-supplied fields, never concatenate strings naively like `tenant + "/" + document` if values could contain the delimiter. Use **canonical per-field framing** (length prefixes, schema/version, UTF-8 charset, null/empty rules) or an agreed standard serialization.

**Check permissions first, check the tag afterward:** a header parsed from a record is untrusted; verify format, size, key namespace, and identity/resource authorization established by the server **before** fetching the key. A valid AEAD tag then proves integrity of ciphertext/AAD. Even with a valid tag, enforce business rules and anti-replay/rollback checks where required.

## 6. Write and Read Workflows in a Multi-Version System

### 6.1 Writing a New Record

```text
1. Authenticate caller, tenant, write permission, and data type.
2. Select activeKeyRef from the service's trusted config/key registry.
3. Generate nonce/IV per policy, unique for the same AES-GCM key.
4. Encode header with formatVersion, immutable key reference, and nonce.
5. Canonicalize AAD from trusted metadata/context; feed AAD.
6. Encrypt plaintext with AES-GCM -> ciphertext || tag.
7. Store full envelope and metadata needed to reconstruct AAD.
8. Emit technical audit (record ID, key version, outcome) without exposing secrets.
```

**Never** accept an arbitrary client-requested `activeKeyId`; encryption keys must be chosen by server policy. During rollouts, distribute the new key and access permissions to all instances before switching the active pointer, preventing older nodes from failing to decrypt newly written records.

### 6.2 Reading an Old Record

```text
1. Authenticate caller and read permission for the exact record/tenant.
2. Receive length-bounded envelope and validate version/profile.
3. Parse key ID as an untrusted routing hint.
4. Verify key ID belongs to an allowed key namespace; never fetch arbitrary keys.
5. Resolve exact key material/version; if unavailable, fail closed.
6. Init AES-GCM with nonce; supply authenticated header and context AAD.
7. Decrypt + verify full tag in doFinal.
8. Only on success return plaintext, parse schema, and execute business logic.
```

**Never** loop “try v2, then v1, then v0 until readable text comes out.” Brute-forcing keys obscures operational failures, widens attack surface, adds latency, and can introduce decryption oracles. Designing with explicit key references lets you **select the exact policy-permitted version**.

If legacy records lack a key ID, establish an **explicit, stage-bounded migration path per data source**, never treating full-keyring guessing as a permanent design. A legacy-version entry point with a dedicated key may exist for controlled migration, but must be strictly scoped and retired once finished.

### 6.3 Separating Key Identification from AEAD Verification

A key ID on the wire is **not authentication proof**. An attacker can alter key IDs and trigger excess KMS calls if the service allows arbitrary IDs. Therefore:

- Accept only formats/versions/IDs within the configured scope.
- Never let an input key ID bypass tenant/resource checks based on trusted data.
- Never leak detailed causes to untrusted callers such as “whether key 1001 for tenant A exists.”
- Include header bytes in AAD to prevent unauthenticated metadata swapping.
- Treat `AEADBadTagException` / `GeneralSecurityException` as hard failure: return zero partial plaintext and never fall back to an unauthenticated mode.
- For large files or streams, never publish any plaintext before the tag is verified; see Section 11.

## 7. Runnable Java 17+ Example: Rotating Without Losing Legacy Data

The example below uses:

- AES-256-GCM, 12-byte random IV, 128-bit tag.
- An **in-memory keyring** simulating a key registry: `1001` is v1, `1002` is v2.
- Binary record with `formatVersion=1`, distinct from `keyId=1001/1002`.
- Header and context included in AAD; every ciphertext/tag byte is authenticated inside `Cipher.doFinal`.
- After rotation, both v1 and v2 remain in the keyring, so **both old and new data** stay readable. After migrating a record to v2 and removing v1 from the map, the migrated record remains readable while the legacy v1 record becomes unreadable.

**Keys in the demo are generated fresh per run**, not a real storage setup. The program only simulates key retention within a single execution. In real systems, keys must persist and be governed in a KMS/HSM/keystore under policy; never hold keys solely in a `static Map` and expect to decrypt data after a service restart.

Save as **`KeyVersionDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class KeyVersionDemo {
    private static final int MAGIC = 0x4b565231; // KVR1
    private static final byte FORMAT_VERSION = 1;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final int HEADER_BYTES = 4 + 1 + 4 + NONCE_BYTES;
    private static final int MAX_RECORD_BYTES = 1_000_000;
    private static final byte[] DOMAIN =
            "document-envelope:v1".getBytes(StandardCharsets.US_ASCII);
    private static final SecureRandom RNG = new SecureRandom();

    private static SecretKey keyFor(Map<Integer, SecretKey> keys, int id)
            throws GeneralSecurityException {
        SecretKey result = keys.get(id);
        if (result == null) {
            throw new GeneralSecurityException("Key unavailable");
        }
        return result;
    }

    private static void setAad(Cipher cipher, byte[] header, byte[] context) {
        cipher.updateAAD(DOMAIN);
        cipher.updateAAD(header);
        cipher.updateAAD(ByteBuffer.allocate(4 + context.length)
                .putInt(context.length).put(context).array());
    }

    static byte[] encrypt(Map<Integer, SecretKey> keys, int activeKeyId,
                          byte[] plaintext, byte[] context)
            throws GeneralSecurityException {
        if (plaintext == null || context == null
                || plaintext.length > MAX_RECORD_BYTES - HEADER_BYTES - TAG_BYTES) {
            throw new GeneralSecurityException("Invalid input");
        }
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        byte[] header = ByteBuffer.allocate(HEADER_BYTES)
                .putInt(MAGIC).put(FORMAT_VERSION).putInt(activeKeyId)
                .put(nonce).array();

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, keyFor(keys, activeKeyId),
                new GCMParameterSpec(TAG_BITS, nonce));
        setAad(cipher, header, context);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return ByteBuffer.allocate(HEADER_BYTES + ciphertextAndTag.length)
                .put(header).put(ciphertextAndTag).array();
    }

    static byte[] decrypt(Map<Integer, SecretKey> keys, byte[] record,
                          byte[] context) throws GeneralSecurityException {
        if (record == null || context == null
                || record.length < HEADER_BYTES + TAG_BYTES
                || record.length > MAX_RECORD_BYTES) {
            throw new GeneralSecurityException("Invalid record length");
        }
        ByteBuffer input = ByteBuffer.wrap(record);
        if (input.getInt() != MAGIC || input.get() != FORMAT_VERSION) {
            throw new GeneralSecurityException("Unsupported format");
        }
        int keyId = input.getInt();
        byte[] nonce = new byte[NONCE_BYTES];
        input.get(nonce);
        SecretKey key = keyFor(keys, keyId);

        byte[] header = Arrays.copyOfRange(record, 0, HEADER_BYTES);
        byte[] ciphertextAndTag = Arrays.copyOfRange(
                record, HEADER_BYTES, record.length);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        setAad(cipher, header, context);
        return cipher.doFinal(ciphertextAndTag);
    }

    static int recordKeyId(byte[] record) {
        return ByteBuffer.wrap(record, 5, 4).getInt();
    }

    @FunctionalInterface
    interface Attempt { void run() throws GeneralSecurityException; }

    static boolean rejected(Attempt attempt) {
        try {
            attempt.run();
            return false;
        } catch (GeneralSecurityException ex) {
            return true;
        }
    }

    public static void main(String[] args) throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        Map<Integer, SecretKey> keyring = new HashMap<>();
        keyring.put(1001, generator.generateKey());
        keyring.put(1002, generator.generateKey());

        byte[] context = "tenant-7/document-42".getBytes(StandardCharsets.UTF_8);
        byte[] payload = "Archive data".getBytes(StandardCharsets.UTF_8);
        byte[] oldRecord = encrypt(keyring, 1001, payload, context);
        byte[] newRecord = encrypt(keyring, 1002, payload, context);

        byte[] tamperedId = oldRecord.clone();
        ByteBuffer.wrap(tamperedId, 5, 4).putInt(1002);
        byte[] tamperedData = oldRecord.clone();
        tamperedData[HEADER_BYTES] ^= 1;
        byte[] tamperedTag = oldRecord.clone();
        tamperedTag[tamperedTag.length - 1] ^= 1;

        byte[] migratedRecord =
                encrypt(keyring, 1002, decrypt(keyring, oldRecord, context), context);
        Map<Integer, SecretKey> newOnly = Map.of(1002, keyring.get(1002));

        System.out.println("Old record key ID: " + recordKeyId(oldRecord));
        System.out.println("New record key ID: " + recordKeyId(newRecord));
        System.out.println("Old readable after rotation: " +
                Arrays.equals(payload, decrypt(keyring, oldRecord, context)));
        System.out.println("New readable: " +
                Arrays.equals(payload, decrypt(keyring, newRecord, context)));
        System.out.println("Tampered key ID rejected: " +
                rejected(() -> decrypt(keyring, tamperedId, context)));
        System.out.println("Wrong context rejected: " +
                rejected(() -> decrypt(keyring, oldRecord,
                        "tenant-8/document-42".getBytes(StandardCharsets.UTF_8))));
        System.out.println("Modified ciphertext rejected: " +
                rejected(() -> decrypt(keyring, tamperedData, context)));
        System.out.println("Modified tag rejected: " +
                rejected(() -> decrypt(keyring, tamperedTag, context)));
        System.out.println("Migrated record key ID: " + recordKeyId(migratedRecord));
        System.out.println("Migrated plaintext preserved: " +
                Arrays.equals(payload, decrypt(newOnly, migratedRecord, context)));
        System.out.println("Old key unavailable blocks legacy record: " +
                rejected(() -> decrypt(newOnly, oldRecord, context)));
    }
}
```

Run with **JDK 17 or higher**:

```bash
javac --release 17 KeyVersionDemo.java
java KeyVersionDemo
```

**Exact stdout** (no random keys/nonces/ciphertexts printed):

```text
Old record key ID: 1001
New record key ID: 1002
Old readable after rotation: true
New readable: true
Tampered key ID rejected: true
Wrong context rejected: true
Modified ciphertext rejected: true
Modified tag rejected: true
Migrated record key ID: 1002
Migrated plaintext preserved: true
Old key unavailable blocks legacy record: true
```

### 7.1 Explaining the Flow and Real Guarantees

- `generator.generateKey()` generates two distinct AES keys for the demo. Production requires a key registry/KMS preserving key material and version states across restarts.
- `encrypt(..., 1001, ...)` writes v1, and `encrypt(..., 1002, ...)` writes v2. **Both share format version 1**; only the key generation differs.
- `setAad` binds domain, header, and length-prefixed context. Changing `keyId` from `1001` to `1002` makes the service select key v2, which fails tag verification because key and AAD mismatch.
- `decrypt` validates length, magic, and format before fetching the key. It **returns `byte[]` only after `Cipher.doFinal` succeeds**, never releasing unauthenticated plaintext.
- Re-encrypting `migratedRecord` **decrypts and authenticates v1 first, then re-encrypts with v2 and a fresh nonce**. It does not merely overwrite the header key ID.
- Map `newOnly` simulates v1 no longer being available to the caller. The v1 record is rejected while the migrated record decrypts. **This simulates a missing key**, not a real KMS destroy operation or key deletion.
- `recordKeyId` is called in `main` solely on records produced by the program itself. It is **not a safe parser for arbitrary input** because it assumes sufficient length and valid layout; `decrypt` performs the minimal validation.
- `rejected` catches `GeneralSecurityException` to illustrate parse/key/AEAD failures. Production systems require clear error handling and auditing without leaking overly granular reasons to untrusted clients.
- Random nonces must not be treated as a mathematical guarantee of **zero** collisions forever. High-volume or multi-node apps need a nonce uniqueness policy and per-key encryption limits per AES-GCM rules.

### 7.2 What the Program Does Not Claim

The program simulates two keys using a local map; it does **not** demonstrate storing secrets in source code, persistence across runs, PKCS#11/KMS/HSM integration, database migration, true multi-tenant isolation, or backup key loss handling. In production, replace `Map<Integer, SecretKey>` with an authenticated, policy-enforced key resolver—typically a KMS/HSM or keystore—and use immutable key version references.

## 8. Rotation Strategies and Legacy Data Preservation

There is no single rotation strategy. Choose based on volume, SLA, storage model, compliance, and risk level.

| Strategy | Must Old Data Change Immediately? | Must Old Key Remain Decryptable? | When Is It Appropriate? |
| --- | --- | --- | --- |
| **New-writes-only rotation** | No | **Yes** while v1 ciphertexts are retained | Need fast switch for new writes and legacy volume is large |
| **Lazy re-encryption** | Changed when a record is read/updated | Yes, until all legacy records migrate/expire | Spread migration load, though rarely read records still need handling |
| **Batch re-encryption** | Yes, via controlled job | Yes throughout migration and rollback window | Want to proactively eliminate dependency on the old key |
| **Rewrap DEK with new KEK** | May **not** require re-encrypting bulk payloads | Old key/KEK needed long enough to unwrap until rewrap finishes | Envelope encryption systems storing wrapped DEKs |
| **Delete/destroy old key** | Does not convert data | **Cannot** decrypt with a lost key | Crypto-shredding when policy accepts losing readability |

### 8.1 New-Writes-Only: Easy to Deploy, Extends Dependency

Switch the active version `v1 -> v2` in the service. All new ciphertexts use v2, while all v1 ciphertexts remain in place. Advantage: fast rollout; drawback: you must protect and retain key v1 **as long as data or backups still require decryption**. A `DECRYPT_ONLY` policy helps avoid accumulating new dependencies on v1.

Holding a key for 10 years because of one unread object adds operational risk and key-retention overhead. Track inventory by key version to decide whether to migrate or expire that data.

### 8.2 Lazy Migration: Read v1, Rewrite v2

Flow:

```text
get(record v1)
   -> decrypt/authenticate with v1
   -> verify caller rights and business state
   -> re-encrypt with active v2 (fresh nonce, correct AAD)
   -> atomic compare-and-swap update if original version unchanged
   -> serve plaintext only after successful verification
```

Advantage: migration load spreads across read traffic. Risks: cold records never migrate automatically; concurrent updates can be overwritten without optimistic locking; migration must not degrade latency or accidentally emit business events.

**Never** consider lazy migration complete until a key-version inventory report confirms zero remaining v1 records or handles untouched records explicitly.

### 8.3 Batch Migration: Must Be Idempotent and Observable

A sound migration job:

1. Snapshots/reads the **exact record version** and legacy AAD metadata.
2. Fetches v1 with decrypt permission; `doFinal` must authenticate successfully.
3. Encrypts plaintext with key v2, a fresh IV, and AAD/context per the new policy.
4. Saves new ciphertext + new key ID + nonce/tag + version/schema in **one transaction or atomic object replacement**.
5. Updates checkpoints only after commit; on failure, the v1 record remains intact.
6. Verifies readback on a sample or all records based on risk; tracks v1/v2 counts and error metrics.
7. Retries using the original version and optimistic locking to prevent lost concurrent updates.
8. Disables/deletes v1 only after all live data and dependent backups/DR/archives have been evaluated.

If interrupted mid-run, the job must be able to rerun **without** turning migrated records unreadable. Because re-encryption produces a new nonce and new ciphertext on every successful attempt, uncommitted retries must never overwrite the source of truth. Never trust a `keyId` from an external request without checking the trusted registry and tenant scope.

### 8.4 Rewrap: Only Applies When Architecture Separates DEK and KEK

**Envelope encryption** typically creates a **DEK** to encrypt content and a **KEK** (often held in KMS) to wrap/unwrap the DEK:

```text
plaintext --encrypt with DEK--> ciphertext + tag
DEK ------wrap with KEK v1--> wrappedDEK-v1

record = ciphertext + nonce + tag + wrappedDEK + KEK reference + metadata
```

When replacing KEK v1 with KEK v2:

```text
unwrap wrappedDEK-v1 using KEK v1 (with permission)
   -> rewrap the same DEK with KEK v2
   -> update wrappedDEK + KEK reference atomically
   -> bulk ciphertext can stay unchanged because DEK did not change
```

**Difference from re-encryption:** changing the **DEK** requires re-encrypting the content with the new DEK and appropriate nonce/tag. Changing only the **KEK** under a supported wrapping mechanism can leave data ciphertext untouched. However:

- Preserve proper metadata/AAD binding, verify key wrapping integrity, and enforce permissions before using the DEK.
- If ciphertext AAD directly binds the KEK version or wrapped DEK metadata, rewrapping alone will invalidate the old tag; design the envelope explicitly for rewrap or re-encrypt per contract.
- A KMS may handle rotating/re-encrypting its key hierarchy in specific ways; never assume “changing a key alias” automatically rekeys any stored record.
- Rewrapping does not cure past exposure if the old DEK or KEK was compromised earlier; apply threat modeling and incident response.

## 9. Binding Metadata: Do Not Let Key ID Become a Tenant-Hopping Vector

A header containing a key ID is **untrusted input** until cryptographic authentication succeeds. In multi-tenant SaaS:

```text
Request identity -> trusted tenant & document permissions
                      |
                      v
Read object by trusted resource ID
                      |
                      v
Parse key reference (untrusted hint)
                      |
                      v
Check key reference belongs to allowed tenant/namespace
                      |
                      v
Decrypt + authenticate header/ciphertext/AAD
                      |
                      v
Validate plaintext schema and business authorization
```

Never allow a user to take ciphertext from tenant A, change the key ID to an ID owned by tenant B, and force the service to call KMS under tenant B's permissions. Even if the tag will fail, that behavior can cause key-access side effects, probe key existence, or bypass IAM scope if the registry lacks checks.

Consider:

- Per-workload/per-tenant KMS permissions blocking cross-tenant key usage from trusted identities.
- Including tenant/document/usage in AAD using an unambiguous serialization.
- Including record ID/version in authenticated data when object swapping must be prevented.
- Domain separation across encryption purposes (documents, tokens, backups) rather than one undifferentiated key.
- Checking that a key ID matches the expected **algorithm, purpose, and region** before use; reject arbitrary attacker-formatted IDs.
- A valid tag never replaces RBAC/ABAC; it only guarantees integrity for the bytes covered by AEAD.

### “Rollback” vs. “Tampering”

GCM proves a ciphertext and AAD are valid under the selected key, **yet it does not prove that ciphertext is the latest version**. An attacker able to replace an object in storage can restore an older valid ciphertext/tag pair unless the application checks a **trusted monotonic version** or anti-rollback state.

If the domain must prevent restoring stale state (e.g., balances, permissions, event ordering), maintain an object version/sequence/state in a trusted database or controlled anti-rollback mechanism. Putting `objectVersion` in AAD only helps if the expected version comes from a source **that cannot be rolled back alongside the ciphertext**.

## 10. Metadata Required to Decrypt Years Later

A ciphertext record must be self-describing or resolvable via durable metadata to perform:

1. Selecting the parser matching `formatVersion` and crypto profile.
2. Locating the **immutable key ID/version** or wrapped DEK + KEK reference.
3. Extracting the nonce and tag of the exact expected lengths.
4. Reconstructing the **exact AAD bytes** under the same policy/version used during encryption.
5. Feeding ciphertext into AEAD in order, releasing plaintext only if the tag passes.
6. Deserializing plaintext according to the matching schema version.
7. Checking authorization for the record and intended operation.

Conceptual data model example (not a mandatory schema):

```text
EncryptedObject {
    objectId: UUID
    tenantId: trusted identifier
    objectRevision: integer
    formatVersion: integer
    cryptoProfile: allowlisted identifier
    immutableKeyRef: opaque string
    nonce: byte[]
    ciphertextAndTag: byte[]
    aadSchemaVersion: integer
    schemaVersion: integer
    state: LIVE | MIGRATING | ARCHIVED | DELETED
}
```

If the key reference sits inside **header AAD**, never update it in the database alone without recomputing the tag. If AAD metadata lives outside the ciphertext, ensure reading it back preserves exact values and serialization across migrations. Never let a newer JSON library alter field ordering or Unicode normalization and break tag verification. For long-lived data, store the exact authenticated AAD bytes or a versioned canonical representation capable of 100% deterministic reconstruction.

**Tag and IV are not secrets**, yet must never be stripped or altered. **Key bytes must be protected separately**, never stored in records or logs. With wrapped DEKs, the wrapped blob is not a plaintext key, yet still needs access control, integrity, and metadata protection by design.

## 11. Safe Decryption: Release Plaintext Only After Tag Verification

When using Java `Cipher` with `AES/GCM/NoPadding`:

```java
// Illustrative snippet inside a method with SecretKey key, byte[] nonce,
// byte[] authenticatedHeader, byte[] trustedContext, and byte[] ciphertextAndTag.
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, nonce));
cipher.updateAAD(authenticatedHeader);
cipher.updateAAD(trustedContext);
byte[] plaintext = cipher.doFinal(ciphertextAndTag);
```

This snippet is **not standalone**; the exact AAD and format must match encryption. `doFinal` throws `AEADBadTagException` (a subclass of `BadPaddingException`) or an equivalent error if the tag is invalid; the application **must never return partially decrypted bytes** in a catch block.

Some streaming providers/modes may emit output from `Cipher.update` **before the final tag is checked**. Never stream those bytes into an HTTP response, event bus, database, log, cache, or file visible to other components. For very large files, use isolated staging with atomic publish after verification, or a **record-based AEAD** format with per-record tags and commitments to order, EOF, and truncation; never stretch an in-memory demo arbitrarily to stream unverified plaintext.

**Note on `CipherInputStream`:** Java documentation warns that this class may catch certain integrity-check exceptions such as `BadPaddingException` without rethrowing them. It **may be unsuitable** where the application must reliably detect authentication failures. Evaluate any streaming API carefully and test end-to-end that zero plaintext escapes on tag failure.

### Length Units

`new GCMParameterSpec(128, nonce)` specifies a **128-bit tag**, i.e., **16 bytes**. The demo IV is 12 bytes. Metadata must explicitly state units and algorithms. Never assume all providers/protocols place the tag in the same position; the Java demo profile relies on `ciphertext || tag` returned by `Cipher.doFinal`.

## 12. Controlling Nonce Uniqueness Across Key Generations

For AES-GCM, **never reuse the same nonce with the same key**. Rotation creates a new key that separates nonce scopes, yet **does not** permit sloppy nonce design or ignoring collision risk. In the example, `SecureRandom` generates a fresh 96-bit IV each time; real applications must account for message volume per key, concurrent encrypting nodes, snapshot restores, counter rollbacks, and key lifetime per standards/guidelines.

Situations requiring vigilance:

- Multiple instances sharing one key and starting the same counter from 0.
- VM snapshot restores causing sequences/counters to repeat.
- Retrying encryption reusing a nonce with **different plaintext/AAD** under the same key.
- Migration jobs reusing v1 nonces when re-encrypting under v2 without a uniqueness guarantee; prefer generating a fresh IV per profile.
- An older key version still encrypting on an un-updated node after switching to decrypt-only.
- Resetting a key alias back to older key bytes, fooling the system into thinking it is a new key while sharing the old key/nonce domain.
- Using random 96-bit nonces at volumes exceeding the evaluated message budget, making collision probability unacceptable.

In a key rotation pipeline, each key generation needs independent **usage limits, a nonce allocation model, and metrics**. With counters, synchronize across nodes and prevent rollbacks; with random nonces, enforce cryptoperiod/message-count caps and timely rotation policies.

## 13. Rollout and Rollback When Multiple Services Read and Write Concurrently

Changing `activeKeyVersion` is more than flipping one config value:

**Preparation phase:**

1. Create key v2 in KMS/keystore with proper policies and permissions.
2. Update consumers/decryptors first so they **can resolve v2** while continuing to read v1.
3. Verify end-to-end tests/health, encrypt/decrypt in staging, failover regions, and backup services.
4. Lock down `formatVersion`/AAD schemas to avoid changing multiple moving parts simultaneously.

**Activation phase:**

1. Switch the active encryption version to v2 via a trusted configuration mechanism.
2. Ensure **one authoritative key-selection policy** is published; during distributed rollouts handle the window where both v1 and v2 writers coexist.
3. Confirm new records use v2 and decrypt across active nodes; ensure v1 stops receiving new writes once rollout completes.
4. Keep v1 in decrypt-only mode until retention and migration complete.

**Post-check phase:**

1. Count live records by key reference, tenant, and environment; monitor failed decrypts by version.
2. Check backups, DR, slow jobs, message queues, archives, and batch exports.
3. Run checkpointed/transactional migrations if required.
4. Transition v1 to disabled/destroyed **only after evidence confirms no readable dependencies remain** or when risk policy forces rejection.

**Rollback:** If v2 writers hit a bug, do not immediately delete/disable v2 — **ciphertexts already written with v2 need key v2 to be read**. Reverting writers to v1 (if policy allows) only changes the key used for future writes; **it does not roll back existing v2 records**. Rollback plans must preserve all key versions referenced by stored data.

### Multi-Region and Backups

A data backup is only useful if the right key can be retrieved to decrypt it **according to permissions and policy**. Maintain a recovery plan covering metadata/key references, KMS availability, trust domains, IAM permissions, and historical key versions.

When restoring a 6-month-old backup, records may still reference v1 even if production moved to v2. If v1 was destroyed, restoration may fail. Conversely, recklessly backing up raw plaintext key material defeats key management. Establish controlled escrow/backup/restore procedures inside protected boundaries with auditing and business continuity alignment.

**Actually test restores**, rather than only checking that backup files exist.

## 14. Deleting a Key Can Mean Deleting Data Readability

A deleted/disabled key can no longer decrypt. If every copy of the relevant DEK/KEK or key material is genuinely destroyed with no recovery path, the corresponding ciphertext becomes **undecryptable** — this is the principle of *cryptographic erasure* in certain designs.

However, do not claim “crypto-erased” just because an entry was removed from config:

- Key copies may remain in backups, caches, logs, snapshots, running instances, or another KMS.
- Exported plaintext copies and downstream data extracts may still exist.
- Under envelope encryption, deleting a KEK can affect many wrapped DEKs; understand the key hierarchy.
- Key rotation and key deletion do not replace data disposal, restricted access, and retention enforcement.
- During a key compromise, deleting the key from the service does not render ciphertext copies already stolen by an attacker safe again.

Therefore, before **destroying** an old key, gather verified inventory of record dependencies, backup retention, and legal/business sign-off. If readable data still depends on a completely lost key, **no Java operation can reconstruct the key from a key ID or ciphertext alone**.

## 15. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using a single `CURRENT_KEY` to decrypt all records | Rotating the key breaks tag checks on old records | Store an immutable key reference on each record |
| Storing alias `latest` without a version | Alias shifts to point at a different key | Store explicit version or KMS blob routing history per contract |
| Treating key ID as secret or embedding key bytes in ID | Key exposure or confused trust boundary | Key ID is a reference only; secrets stay in the key manager |
| Sharing one `version` for format, key, and schema | Ambiguity over parsing vs. key selection | Separate version fields by meaning |
| Automatically trying the whole keyring on decrypt | Ambiguous errors, wasted resources, decryption oracle | Look up one exact key version via metadata/registry |
| Letting clients choose arbitrary keys | Cross-tenant lookup/key abuse | Scope by tenant, identity, and server-side IAM/allowlist |
| Omitting key ID/header from AEAD authentication | Metadata can be swapped undetected | Include header in AAD; validate profile and key scope |
| Leaving v1 ACTIVE on stale nodes after rotation | New data continues depending on old key | Enforce decrypt-only state and monitor writers |
| Changing only header v1 to v2 during migration | Ciphertext/tag remain bound to old key/nonce/AAD | Decrypt + verify, then re-encrypt with v2 + fresh nonce |
| Deleting v1 immediately upon activating v2 | Loss of ability to read/restore legacy ciphertexts | Retain in decrypt-only until dependencies are zero |
| Forgetting backups/DR/queues when counting key usage | Failed restores or jobs still needing old keys | Maintain full inventory across storage locations and retention windows |
| Migration writing new key ID before ciphertext/tag | Half-migrated state, data corruption | Atomic transaction, object replacement, or compare-and-swap |
| Rewrapping KEK while AAD embeds KEK metadata | Payload tag may become invalid | Design envelope specifically for rewrap or re-encrypt |
| Re-encrypting while reusing nonces on the same key | Risk of breaking GCM security | Enforce nonce uniqueness across the key's entire lifetime |
| Treating a valid tag as proof of latest record | Replay/rollback of stale ciphertexts | Use trusted monotonic revision or anti-rollback state |
| Publishing plaintext from `Cipher.update` before tag check | Unauthenticated data escapes trust boundary | Commit/publish only after `doFinal` succeeds |
| Switching active pointer, rolling back, and deleting v2 | Newly written v2 records become unreadable | Retain every key version that ever wrote persisted data |
| Logging keys, plaintext, or raw wrapped DEKs | Sensitive data exposure | Audit sanitized metadata with access controls |

## 16. Rotation Testing and Acceptance Checklist

Minimum automated test suite to run in CI/staging before every rollout:

| Test Case | Expected Outcome |
| --- | --- |
| Write v1 then switch ACTIVE to v2 | v1 records still decrypt with v1 while policy allows |
| Write new record after switch | Envelope contains immutable v2 key ref; decrypts with v2 |
| Transition v1 to DECRYPT_ONLY | Zero new writes under v1; v1 records remain readable |
| Disable/lose v1 key | v1 records fail clearly without trying other keys |
| Alter key ID from v1 to v2 in header | AEAD authentication fails |
| Alter IV, ciphertext, or tag | Rejected; zero plaintext returned |
| Alter tenant/document context AAD | Tag fails; plaintext never used |
| Unsupported format version | Parser rejects; no weak fallback |
| Migrate v1 -> v2 | Decrypt/authenticate v1, then encrypt v2 with fresh IV; content identical |
| Migration interrupted before commit | v1 record intact; retry is idempotent |
| Two migration workers hit the same record | Optimistic lock/CAS prevents overwriting newer revision |
| Roll back writer after v2 records exist | v2 records remain decryptable |
| Backup/DR restore | System resolves exact key versions per policy and role |
| Legacy records still in archive | Old key cannot be destroyed while archive recovery is required |
| Tenant A header points to tenant B key | Scope authorization rejects before key use |
| Forged/oversized/non-existent key ID | Bounded parsing, lookup rejected, no key details leaked |
| Attempted nonce reuse with same key | Nonce allocation/limit tests and controls detect/prevent per design |
| Replay of an older valid record | Anti-replay/anti-rollback policy handles via trusted state |
| Migration performance | Quotas/rate limits, backoff, checkpoints, and auditing in place |
| Auditing | Logs record ID, key reference, migration result; zero keys/plaintext exposed |

**Rotation completion criteria:** not merely “new data encrypts with v2.” You must verify v1/v2 decryption per policy, zero data corruption during migration, tested backup restores, old-key retirement aligned with retention, and zero out-of-policy key access.

## 17. Practice Exercises

### Exercise 1 — Distinguishing Version Types

Given a record with `formatVersion=2`, `keyRef=orders/prod`, `keyVersion=5`, and `documentSchemaVersion=3`, describe what each version governs, which values may change during re-encryption, and why reading only `keyRef=orders/prod` fails if the alias moves to new key material.

### Exercise 2 — Analyzing Program Output

Run `KeyVersionDemo` and explain every stdout line. Add tests that flip one byte in the nonce/header, flip one bit in the tag, truncate the entire record, and pass an un-allowlisted `formatVersion`. Prove `decrypt` returns no plaintext when the tag is invalid.

### Exercise 3 — Designing a Lifecycle Policy

A system holds 3 million v1 records, 10,000 v2 records, weekly snapshots retained for 180 days, and archives retained for 7 years. Propose `ACTIVE`/`DECRYPT_ONLY`/`DISABLED` states, KPIs per key version, a batch migration plan, and when v1 may be destroyed. Distinguish live record counts from backup copies that still require restoration.

### Exercise 4 — Lazy Migration and Optimistic Locking

Design a table `EncryptedDocument(id, revision, keyVersion, encryptedEnvelope)`. Two concurrent requests read a v1 record and both try to migrate it to v2. Write transaction/CAS pseudocode ensuring only one update commits and the other never overwrites a newer revision. Describe retry behavior and how to avoid duplicate business side effects.

### Exercise 5 — Rewrapping DEK and KEK

A service encrypts each object with its own DEK; KMS uses KEK v1 to wrap the DEK. When the KEK rotates to v2, what can remain unchanged and what must be updated? Explain why this differs from a system using **a single AES key directly to encrypt every object**, and how to handle it if the ciphertext's AAD included the KEK version.

### Exercise 6 — Disaster Recovery

After switching the active key to v2, one region fails and operations restores a backup containing both v1 and v2 ciphertexts. List the required key versions, IAM permissions, AAD metadata, key availability, and code versions. Describe failure scenarios where restoration cannot complete even though the backup file is intact.

### Exercise 7 — Compromise and Cryptographic Erasure

Key v1 is suspected compromised while 100,000 records still depend on it. Prioritize containment, scoping potentially exposed data, migration, key disable/revoke, backup/key retention, and policy-driven incident reporting. Why can re-encryption not make data “secret again” if an adversary already captured plaintext earlier?

**Expected outcomes:** you can inspect a ciphertext and determine **which key to use, which format version applies, which metadata must be authenticated, how to read legacy data across rotation**, and when **a key must not be destroyed**. A complete implementation always tests missing/wrong keys, tampering, replay/rollback per threat model, and migration transaction safety.

## 18. References

- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `init`, `updateAAD`, `doFinal`, and AEAD.
- [Java SE 17 — GCMParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): IV/nonce and tag length in bits.
- [Java SE 17 — KeyGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html): generating secret keys by algorithm/provider.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): cryptographic random byte source.
- [NIST SP 800-57 Part 1 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): key lifecycle and management.
- [NIST SP 800-38D — Galois/Counter Mode (GCM)](https://csrc.nist.gov/pubs/sp/800/38/d/final): AEAD and IV/nonce requirements.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): key, data, and rotation management.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): lifecycle, storage, access control, and rotation.
