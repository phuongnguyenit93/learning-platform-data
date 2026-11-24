# 7.7. Distinguishing Password-Based Encryption from Randomly Generated Keys

## Learning objectives

Upon completing this lesson, you will be able to:

1. Explain why **human-chosen passwords** and **randomly generated cryptographic keys** come from completely different strength sources, even when both end up as a 32-byte AES-256 key.
2. Accurately describe the **password-based encryption (PBE)** workflow: password → KDF with salt and work factor → key → authenticated encryption; distinguish **salt**, **nonce**, **key**, **authentication tag**, and required stored metadata.
3. Decide when to **derive a key directly from a password**, when to **generate a random data encryption key (DEK)**, and when to use **envelope encryption** with a DEK wrapped by a key encryption key (KEK) derived from a password or managed by a KMS/HSM.
4. Understand offline password-guessing costs, password changes, data recovery, key rotation, and the risks when a system loses a password or key.
5. Implement a **Java 17+** example using `PBKDF2WithHmacSHA256`, `SecureRandom`, `KeyGenerator`, and `AES/GCM/NoPadding`; verify that both wrong passwords and modified ciphertexts are rejected.

**Scope:** This lesson belongs to the *Passwords and Key Derivation* section of Java Advance security-cryptography. The focus is on **architectural protection of data with passwords vs. randomly generated keys**, not on storing user login passwords or designing custom cryptographic algorithms.

---

## 1. Two key sources lead to two different security levels

A system has sensitive data that needs AES-GCM encryption. The developer faces two initial options:

- The user remembers a **password/passphrase** to decrypt later. The program cannot directly use a character string as a proper AES key; it must **derive** the key from the password using an algorithm like PBKDF2, scrypt, or Argon2id with agreed parameters.
- The system uses a cryptographically secure random number generator (**CSPRNG**) to generate a **random AES key**. The key may reside in a KMS/HSM, a protected keystore, or be wrapped by another key. Users typically do not need to memorize this key.

For example, suppose an easily guessable passphrase is fed through PBKDF2 to produce 32 bytes. Although the output is 256 bits long and *looks* random, an attacker can try a password list, rerun the KDF, and check against the ciphertext. **The KDF increases the cost per guess; it does not turn a low-entropy password into a truly strong 256-bit secret.**

Conversely, 32 bytes properly generated at random from `KeyGenerator`/`SecureRandom` have a vast key space unconstrained by human memorability. The challenge of this approach is **key distribution and custody**: losing the key makes decryption impossible, while leaking the key exposes the ciphertext.

### 1.1. Data flow models

**Direct PBE:**

```text
User-entered password
             │
             ├── Unique random salt per encryption setup
             ├── KDF algorithm and work factor
             ▼
       Password KDF (intentionally slow)
             │
             ▼
        Derived AES key
             │                 Fresh nonce/IV
             └────────────┬─────────┘
                          ▼
                    AES-GCM
                          │
             Ciphertext + authentication tag
```

**Random key:**

```text
CSPRNG / KeyGenerator
           │
           ▼
   Random AES key ────────────────────┐
           │                          │ store or wrap securely
           ▼                          ▼
AES-GCM(data, fresh nonce)        KMS / HSM / keystore
           │
Ciphertext + authentication tag
```

You can also choose a third approach: **encrypt data with a random DEK, then use a password-derived KEK to wrap the DEK**. On a password change, some architectures only need to rewrap the DEK rather than re-encrypting all data. This is **envelope encryption**, analyzed in section 6.

## 2. Comparison table: password-based encryption vs. randomly generated keys

| Aspect | Direct PBE (password → KDF → key) | Randomly generated key (CSPRNG → key) |
| --- | --- | --- |
| Source of secrecy | Password/passphrase supplied by a human or input flow | Cryptographic-quality random generator |
| Practical strength | Bounded by password entropy and KDF attack cost | Can achieve full random-key and cipher strength when properly generated |
| What is needed to get the key | **Correct password**, **salt**, **KDF/parameters** | Access to stored key or authorized unwrapping mechanism |
| Key setup speed | **Intentionally slow** to hinder password brute force | Usually faster: generated via `KeyGenerator`, no slow password KDF |
| Salt | **Mandatory/essential** for password derivation; should be fresh and unique | No salt needed to generate a raw AES key from a CSPRNG |
| AES-GCM nonce | **Still required**, independent of salt | **Still required**, regardless of the key being randomly generated |
| Authentication tag | **Still required** to detect tampering/wrong key | **Still required** to detect tampering/wrong key |
| Offline guessing risk | Yes: anyone holding ciphertext+salt can test passwords without contacting a server | No “password guessing” if data is protected solely by a password-independent random key |
| Secret storage | No need to store password; store PBE metadata to recreate the key | Must store/wrap the DEK or future decryption becomes impossible |
| Password change | Typically must decrypt and re-encrypt if key is directly derived | Unaffected if the key is independent of passwords |
| Rotation / revocation | Changing password/cost/salt changes the key; requires a migration plan | Rotate/re-encrypt or rewrap key via KMS/KEK |
| Recovery | Depends on remembering or recovering the password | Depends on backups/key escrow/KMS recovery controls |
| Best suited for | Personal files/vaults, passphrase-unlocked backups, user-held secret requirements | Backend services, DB/application encryption, large datasets, centralized key lifecycle |
| Typical risks | Weak password, too-fast KDF, reused salt, password logged, offline guessing | Hardcoded key, leaked KMS credentials, lost key/backup, nonce reuse, improper key sharing |

**What they share:** Both ultimately produce an AES `SecretKey` and use **the exact same** `Cipher.getInstance("AES/GCM/NoPadding")`. Distinguishing PBE from random-key encryption is mainly about **key origin, guessability, key recovery, and lifecycle governance**, not that “PBE's AES” is a different AES algorithm.

## 3. PBE is a multi-step process, not “AES(password)”

PBE requires two distinct components:

1. **Password-Based Key Derivation Function (KDF)** to convert a password into key material using a salt and work factor.
2. **Encryption scheme** using that key to encrypt data, preferably an AEAD with an authentication tag.

Example:

```text
password: char[]
salt: 16 random bytes
KDF: PBKDF2-HMAC-SHA256, iterations = configured parameter
derivedKey: 32 bytes
nonce: fresh 12 bytes for AES-GCM
ciphertextAndTag: doFinal(plaintext) via AES/GCM/NoPadding
```

Parameters such as **KDF algorithm, iteration count, key size, salt, encryption algorithm, nonce, version, and tag format** must be stored with the ciphertext or retrieved reliably. The recipient uses the same password and exact same metadata to recreate the key and decrypt.

### 3.1. Why is a slow KDF needed?

Human-chosen passwords often contain predictable patterns. If an application does:

```java
// Wrong for PBE: SHA-256 is too fast, lacking work factor and salt.
byte[] aesBytes = java.security.MessageDigest
        .getInstance("SHA-256")
        .digest(new String(password)
                .getBytes(java.nio.charset.StandardCharsets.UTF_8));
```

This is an **anti-pattern illustration**, not production code. SHA-256 runs very fast, letting attackers test millions of passwords. Creating a `String` from the password also leaves copies that are hard to purge from memory.

Password KDFs are designed to make every guess consume **CPU and/or RAM**:

- **PBKDF2-HMAC-SHA256:** available via `SecretKeyFactory` across standard JDK 17 distributions; the work factor is the iteration count. Convenient for pure-JDK apps and environments requiring standardization/FIPS when using an approved provider.
- **scrypt:** a memory- and CPU-intensive KDF that resists mass password-cracking hardware. Do not assume it is a built-in standard API in every Java SE 17 runtime; use an evaluated library.
- **Argon2id:** a memory-hard KDF commonly recommended for modern applications. Java SE 17 has no standard `Argon2id` class; using it requires an appropriate library/provider and parameter controls.
- **Legacy PBE algorithms** such as `PBEWithMD5AndDES`, DES, or weak PBKDF settings must never be chosen for new designs merely because their names contain `PBE`.

PBKDF2 iteration counts must stay updated with organizational policy and hardware. For instance, the OWASP Password Storage Cheat Sheet recommends **PBKDF2-HMAC-SHA256 with 600,000 iterations or more for password storage** at the time of reference; that is **not a universal constant for every PBE file**, nor a substitute for benchmarking against latency, threat model, resources, and DoS risks. Each ciphertext must record the actual work factor used so decryption and future upgrades work.

### 3.2. What role does the salt play?

A salt is random bytes that **do not need to be secret**, generated uniquely for each password-based key derivation setup. If a user uses the same password for two files with separate salts, the KDF generates two distinct keys with overwhelming probability. An attacker cannot reuse one precomputed hash/key-derivation result across ciphertexts with different salts.

In Java:

```java
SecureRandom rng = new SecureRandom();
byte[] salt = new byte[16];
rng.nextBytes(salt);
```

This is an **in-method snippet** requiring `import java.security.SecureRandom;`. A 16-byte salt is a common choice. **A salt does not substitute for a high-entropy password and does not eliminate offline guessing attacks.**

Avoid: a hardcoded salt shared across all data, using an email address as the sole salt for all file versions, substituting timestamps for a random salt, or thinking the salt must be hidden like a secret. When re-deriving the key to decrypt, use **the exact salt stored with that ciphertext**, not a newly generated salt.

### 3.3. Salt differs from the AES-GCM nonce/IV

| Property | KDF Salt | AES-GCM Nonce/IV |
| --- | --- | --- |
| Used in | `PBKDF2WithHmacSHA256` / password KDF | `AES/GCM/NoPadding` |
| Purpose | Make each key derivation distinct; thwart precomputation across ciphertexts | Ensure encryptions under the **same key** never repeat a nonce |
| Secret? | No | No |
| In the demo | 16 bytes | 12 bytes |
| Can store with ciphertext? | Yes, required to recreate the key | Yes, required to decrypt |
| Can be static? | Should not be: loses per-derivation salt uniqueness | **Must never** reuse a nonce when encrypting under the same key |
| Changes on decryption? | No, must reuse original salt | No, must reuse original nonce |

Even though both salt and nonce can be generated with `SecureRandom`, **they are two separate protocol fields**; never assume one can replace the other. With AES-GCM, reusing a *(key, nonce)* pair is a critical flaw that can break confidentiality and authentication. Even if every file has a fresh salt, you must still manage nonces properly per key for every encryption.

### 3.4. Having the right password is not enough: authenticate the ciphertext

Encryption provides **confidentiality**, yet without integrity/authentication, encrypted data can be altered or swapped undetected by the backend. Prefer **AEAD** such as AES-GCM (or another vetted standard AEAD) for new PBE designs.

A conceptual record:

```text
version | kdf-id | iterations | salt | enc-id | nonce | ciphertext | tag
             \_______________ authenticated metadata _______________/
```

Authenticating metadata only works if **the workflow actually feeds those bytes into AAD or a MAC/tag-protected region**. If version/iterations/salt can be altered without controlled validation, the system can fail, misbehave, or suffer resource exhaustion. With GCM, ciphertext and tag can be stored concatenated; the receiver must confirm tag verification succeeds before using plaintext.

**Do not use unauthenticated CBC/ECB** for PBE on new data. A transformation named `PBEWithHmacSHA256AndAES_256` does not by itself guarantee the underlying mode is an AEAD with a tag. Inspect the specification/provider and add separate integrity verification if the PBE algorithm lacks authentication.

## 4. Offline password guessing: the fundamental limit of PBE

Suppose an attacker obtains:

```text
salt + iterations + nonce + ciphertext + authentication tag
```

The adversary does not need to send any request to your server to guess the password. They can:

1. Pick a candidate password from a dictionary or known password-mutation rules.
2. Run the same `KDF(candidate, storedSalt, storedIterations)` to generate a trial key.
3. Attempt to decrypt/verify the ciphertext; if the authentication tag fails, discard the candidate and try the next.
4. Repeat massively on GPUs/CPUs/specialized hardware as permitted by the KDF.

This is **offline password guessing**. Rate limiting, CAPTCHAs, or account lockouts on your API **cannot stop offline password trials against a stolen ciphertext copy**. Each guess has a cost raised by the KDF, yet an overly weak password can still be found.

This creates a sharp contrast with **a true random key held inside a KMS/HSM**: if an adversary only has ciphertext and lacks permission to fetch the key or unwrap the DEK, there is no human dictionary password they can test to recreate the key. They would have to compromise key governance, steal access credentials, exploit the system, or break the primitive—a fundamentally different threat model.

**Technical conclusion:** KDF output length **does not directly measure password entropy**. A 256-bit key derived from `"123456"` still faces a tiny password-guessing space. A strong KDF plus a sufficiently strong password are mandatory for PBE; there are no shortcuts via hashing or Base64.

### 4.1. Can a pepper rescue a weak password?

A **pepper** is a system-side secret (e.g., kept in a KMS/HSM) that can be combined via a carefully designed workflow for defense in depth. Pepper **differs from salt**: salt is public and per-record; pepper must remain secret. If ciphertext, weak password, and pepper all leak, that layer no longer helps.

For **offline PBE where users must decrypt on their own without contacting a server**, requiring a pepper from an external service can break offline usability. If the goal is a user-held backup, weigh that trade-off explicitly rather than adding a pepper unconditionally.

## 5. Random keys: why do they avoid password entropy limits?

In Java:

```java
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, new SecureRandom());
SecretKey dataKey = generator.generateKey();
```

This is an **illustrative Java snippet**, requiring `javax.crypto.KeyGenerator`, `javax.crypto.SecretKey`, `java.security.SecureRandom`, and checked-exception handling. On standard JDK 17 providers, this generates a 256-bit AES key from an appropriate CSPRNG rather than deriving from a guessable password.

Yet **random generation is only half the story**:

- The key must be stored/protected in an appropriate system; never hardcode keys in source, JSON configs, or expose them in logs.
- Define key ownership policy: user, tenant, service, object, or data version?
- Do you have backup/rotation, read/unwrap access controls, and a recovery process?
- You can use a KMS/HSM to hold a **KEK** or generate/unwrap a **DEK**; when encrypting locally, manage plaintext DEKs in memory and zero them appropriately.
- If a key is lost with no proper backup/escrow, the data **may become permanently unrecoverable**, even with intact ciphertext.
- Even with a strong random key, encryption still requires non-repeating IVs/nonces, AEAD tags, and proper schemas/authorization.

In backend environments handling millions of records, **random keys and envelope encryption** typically make rotation, access control, auditing, and per-service storage far more manageable than relying on a shared password across all data.

### 5.1. Should you use `SecureRandom.nextBytes` instead of `KeyGenerator`?

You can generate bytes with `SecureRandom` and construct a `SecretKeySpec` when the algorithm permits and length/quality are ensured. However, `KeyGenerator` clarifies **the intent to create a key for a specific algorithm**, validates key sizes, and integrates smoothly with providers. When an HSM/KMS creates non-exportable keys (`getEncoded()` unavailable), key management differs from raw bytes in this example.

Never use `Random`, `ThreadLocalRandom`, `Math.random()`, or `UUID.toString()` casually to create AES keys. UUID v4 has fixed version/variant bits and cannot be treated as a full-entropy AES-256 key. Never use secrets derived from database IDs or timestamps as raw keys.

## 6. Envelope encryption: combining passwords and random keys

**Envelope encryption** separates:

- **DEK (Data Encryption Key):** a randomly generated key that encrypts the data.
- **KEK (Key Encryption Key):** a key used to **wrap/protect the DEK**. The KEK can be derived from a password via a KDF or held by a KMS/HSM.

Sample flow for a password-protected user file:

```text
                  User password
                       │ + salt + KDF parameters
                       ▼
                      KEK
                       │
Random DEK ────────────┼──> Wrap DEK with KEK ──> wrappedDEK
    │                  │
    │                  └──── Protect corresponding metadata/version/policy
    ▼
AES-GCM encrypt data with DEK + dataNonce
    │
ciphertext + tag

Store: file format/version | KDF params | salt
       KEK wrapping nonce | wrappedDEK + wrap tag
       data nonce | data ciphertext + data tag | AAD/context
```

Here, **key wrapping** requires an integrity-protected mechanism (such as AES-KW or proper AEAD), nonce/key discipline, and metadata binding—never just XORing the DEK with a password hash. If two AEAD layers use the same cipher, use independent keys and manage **separate nonces per key/encryption**.

### 6.1. Advantages over direct PBE

| Operation | Direct PBE | Random DEK + password-derived KEK |
| --- | --- | --- |
| Encrypt large file | Encrypt with password-derived key | Encrypt file with random DEK |
| Open file | KDF password → key → decrypt data | KDF password → KEK → unwrap DEK → decrypt data |
| Password change | Must decrypt/re-encrypt entire file (or use another migration design) | Unwrap DEK with old KEK and **rewrap DEK** with new KEK, leaving data ciphertext untouched |
| Work factor upgrade | Typically changes derived key, requiring ciphertext regeneration | Can rewrap DEK at new cost |
| Multi-GB data | Re-encrypting on password change can be very I/O heavy | Rewrapping DEK processes only small key material |
| Granting access to multiple users | Awkward if everyone must share one password or store duplicate ciphertexts | Same DEK can be wrapped per recipient under distinct mechanisms/KEKs |
| Offline password guessing risk | Yes | **Still yes** if wrappedDEK and salt are obtained; separating DEK does not strengthen a weak password |

**Crucial point:** a random DEK wrapped by a password-derived KEK **does not eliminate offline dictionary attacks on the password**, because an attacker can try unwrapping the DEK. The primary benefit of envelope encryption here is **separating the data key from the access key**, simplifying password changes, multi-party sharing, and changing how the KEK is protected.

To resist password guessing against stolen ciphertexts, users must have sufficiently strong passwords and a proper KDF, or the system must incorporate an independent centrally managed KMS/HSM secret and access controls.

### 6.2. When the KEK resides in a KMS/HSM

A backend can use a random DEK to encrypt payloads and store only the **wrapped DEK** alongside ciphertext. When decryption is authorized, the service calls the KMS to unwrap the DEK within a defined permission scope. This is a **key-management-service architecture**, distinct from having a human memorize a password.

Pros: IAM controls, policies, auditing, master keys, and system-wide rotation/backup. Limits: service/network/availability dependencies, cost, application permission scope, and exposure of keys/credentials in RAM. **KMS does not replace application authorization**: your API must still verify tenant/record access before requesting an unwrap.

### 6.3. Considerations when changing passwords and rotating keys

If an old password leaked and an attacker kept a **copy of the old `wrappedDEK`**, changing the password and overwriting the header **does not make the stolen copy safe**. Likewise, KMS key rotation does not automatically invalidate old ciphertexts/DEKs exposed earlier. Assess which data was exposed, revoke access, rotate DEKs, and re-encrypt when your threat model demands it.

You can retain an old DEK to read legacy data during migration, provided you have key versions and a retirement process. Never merely bump the iteration count or swap the salt **in metadata** without performing proper derivation/rewrapping/re-encryption: the data will become undecryptable.

## 7. Data format that must be stored to decrypt years later

Direct PBE example using PBKDF2-HMAC-SHA256 and AES-GCM:

```text
+----------+---------+------------+----------+----------+----------+----------------+
| format v | kdf id  | iterations | salt     | nonce    | enc id   | ciphertext+tag |
+----------+---------+------------+----------+----------+----------+----------------+
    1 byte    enum       int          16 B       12 B      AES-GCM     arbitrary
```

This diagram is descriptive only; **it is not an official wire byte layout**, and real formats require field lengths, endianness, AAD, versioning, payload caps, authenticated parsing, and downgrade protections.

Essential metadata fields:

| Field | Secret? | Why is it needed? |
| --- | --- | --- |
| Format version | No | Know how to parse/migrate; reject invalid versions |
| KDF name and PRF | No | Recreate the exact key from the password |
| Iteration count / memory cost / parallelism | No | Reproduce the exact work factor used |
| Salt | No | Derive the same key from the password |
| Cipher mode, key size, tag size | No | Select the exact transformation and parameters |
| Nonce/IV | No | Decrypt properly; during encryption, ensure uniqueness per key |
| Ciphertext + authentication tag | Tag needs no secrecy; **plaintext is protected** | Store payload and verify integrity |
| Key ID or wrapped DEK (if envelope) | Not raw secret keys; must protect integrity | Select the right key and unlock data |
| Secret password / raw random key / plaintext KEK | **Yes** | **Never** place in ciphertext/headers/logs in raw form |

Never keep PBE parameters solely in “current” application config that changes a few months later. When KDF cost rises, old files must be **read with their exact old parameters**, then migrated/re-encrypted in a controlled manner. If a KDF id is stored in an attacker-controlled header, enforce **allowlists, resource bounds, and authenticated metadata** to prevent downgrades, DoS, or parser exploits.

### 7.1. AAD protects context

AEAD supports **AAD (Additional Authenticated Data)**: metadata that is **authenticated but not encrypted**. Examples suitable for AAD include version, KDF parameters, salt/nonce if designed so, tenant ID, object ID, content type, and application permissions/context. Decryption must supply the exact same AAD; any mismatch fails tag verification.

Never put secrets into AAD expecting encryption; AAD is typically stored/transmitted in the clear. Never pass plaintext to the application before GCM tag verification completes. A valid GCM ciphertext can still be **replayed** intact; prevent replay with sequence numbers, IDs, or business state.

## 8. Java 17+ example: PBE with PBKDF2 + AES-GCM vs. randomly generated AES key

Create **`PasswordVsRandomKeyDemo.java`**. This standalone Java 17+ program demonstrates two branches:

- **Direct PBE:** derives AES-256 from a password, a 16-byte random salt, and PBKDF2-HMAC-SHA256; encrypts with AES-GCM and a 12-byte nonce. The record stores KDF parameters needed for later decryption. Header version + iterations + salt + nonce are bound into AAD.
- **Random key:** generates AES-256 directly via `KeyGenerator` and encrypts the same plaintext with AES-GCM using a fresh nonce. The key lives only inside this demo with no storage/recovery.
- Tests a wrong password and a modified tag to prove **no plaintext is returned when authentication fails**. Stdout prints only booleans and lengths, never exposing passwords or keys.

**Note before running:** The fixed password string below **is demo data only—never hardcode passwords in real applications**. The iteration count is an explicit illustrative value and should be benchmarked/tuned per current policy. The code uses `PBKDF2WithHmacSHA256` available on common JDK 17 builds; specialized providers may require different setup. `record` is valid Java 17 syntax.

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

public class PasswordVsRandomKeyDemo {
    private static final SecureRandom RNG = new SecureRandom();

    private static final int ROUNDS = 600_000; // Demo; tune for your system.
    private static final int SALT_BYTES = 16;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int KEY_BITS = 256;
    private static final byte VERSION = 1;

    // In-memory record: production requires proper serialization and defensive copies.
    private record PasswordEnvelope(
            int iterations, byte[] salt, byte[] nonce, byte[] ciphertextAndTag) {}

    private static SecretKey derivePasswordKey(
            char[] password, byte[] salt, int iterations)
            throws GeneralSecurityException {

        PBEKeySpec spec =
                new PBEKeySpec(password, salt, iterations, KEY_BITS);
        byte[] material = null;
        try {
            SecretKeyFactory kdf =
                    SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
            material = kdf.generateSecret(spec).getEncoded();
            // SecretKeySpec copies the key bytes before zeroing the temporary buffer.
            return new SecretKeySpec(material, "AES");
        } finally {
            if (material != null) {
                Arrays.fill(material, (byte) 0);
            }
            spec.clearPassword();
        }
    }

    private static byte[] header(
            int iterations, byte[] salt, byte[] nonce) {
        return ByteBuffer.allocate(1 + 4 + salt.length + nonce.length)
                .put(VERSION)
                .putInt(iterations)
                .put(salt)
                .put(nonce)
                .array();
    }

    private static PasswordEnvelope encryptWithPassword(
            char[] password, byte[] plaintext)
            throws GeneralSecurityException {

        byte[] salt = new byte[SALT_BYTES];
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(salt);
        RNG.nextBytes(nonce);

        SecretKey key = derivePasswordKey(password, salt, ROUNDS);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(header(ROUNDS, salt, nonce));
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return new PasswordEnvelope(ROUNDS, salt, nonce, ciphertextAndTag);
    }

    private static byte[] decryptWithPassword(
            char[] password, PasswordEnvelope stored)
            throws GeneralSecurityException {

        // Enforce resource and format bounds before running the KDF.
        if (stored.iterations() < 100_000
                || stored.iterations() > 2_000_000
                || stored.salt().length != SALT_BYTES
                || stored.nonce().length != NONCE_BYTES
                || stored.ciphertextAndTag().length < TAG_BITS / 8) {
            throw new GeneralSecurityException("Invalid envelope");
        }

        SecretKey key = derivePasswordKey(
                password, stored.salt(), stored.iterations());
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, stored.nonce()));
        cipher.updateAAD(header(
                stored.iterations(), stored.salt(), stored.nonce()));
        return cipher.doFinal(stored.ciphertextAndTag());
    }

    private static SecretKey generateRandomKey()
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(KEY_BITS, RNG);
        return generator.generateKey();
    }

    private static boolean randomKeyRoundTrip(byte[] plaintext)
            throws GeneralSecurityException {
        SecretKey key = generateRandomKey();
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        byte[] ciphertextAndTag = encrypt.doFinal(plaintext);

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        return Arrays.equals(plaintext, decrypt.doFinal(ciphertextAndTag));
    }

    public static void main(String[] args) throws Exception {
        // DEMO ONLY: production reads password from secure input.
        char[] password = "classroom-demo-only".toCharArray();
        char[] wrong = "wrong-password".toCharArray();
        try {
            byte[] plaintext = "PBE vs random data key"
                    .getBytes(StandardCharsets.UTF_8);

            PasswordEnvelope stored =
                    encryptWithPassword(password, plaintext);
            boolean pbeRoundTrip = Arrays.equals(
                    plaintext, decryptWithPassword(password, stored));

            boolean wrongRejected = false;
            try {
                decryptWithPassword(wrong, stored);
            } catch (AEADBadTagException expected) {
                wrongRejected = true;
            }

            byte[] changed = stored.ciphertextAndTag().clone();
            changed[changed.length - 1] ^= 1;
            PasswordEnvelope tampered = new PasswordEnvelope(
                    stored.iterations(),
                    stored.salt(),
                    stored.nonce(),
                    changed);
            boolean tamperRejected = false;
            try {
                decryptWithPassword(password, tampered);
            } catch (AEADBadTagException expected) {
                tamperRejected = true;
            }

            System.out.println("pbeRoundTrip=" + pbeRoundTrip);
            System.out.println("wrongPasswordRejected=" + wrongRejected);
            System.out.println("pbeTamperRejected=" + tamperRejected);
            System.out.println("saltBytes=" + stored.salt().length);
            System.out.println("pbeNonceBytes=" + stored.nonce().length);
            System.out.println("randomKeyRoundTrip=" +
                    randomKeyRoundTrip(plaintext));
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
```

Compile and run with a JDK 17+ supporting these algorithms:

```shell
javac PasswordVsRandomKeyDemo.java
java PasswordVsRandomKeyDemo
```

**Expected stdout** (key, salt, and nonce are random so the code intentionally omits printing them):

```text
pbeRoundTrip=true
wrongPasswordRejected=true
pbeTamperRejected=true
saltBytes=16
pbeNonceBytes=12
randomKeyRoundTrip=true
```

### 8.1. Interpreting every output line

- `pbeRoundTrip=true`: identical password + salt + iterations recreate the same AES key; matching nonce and AAD metadata let GCM verify and return the original plaintext.
- `wrongPasswordRejected=true`: a different password produces a different key; the GCM authentication tag is invalid and throws `AEADBadTagException`. This detects failed decryption—**it is not a rate-limiting service for offline password trials**.
- `pbeTamperRejected=true`: flipping a tag byte fails authentication. Never catch `AEADBadTagException` and still pass unverified/stale plaintext to business logic.
- `saltBytes=16` and `pbeNonceBytes=12`: there are **two distinct fields** with different roles, both stored with ciphertext when needed for decryption.
- `randomKeyRoundTrip=true`: the same AES-GCM cipher, yet the key is randomly generated by `KeyGenerator`, requiring neither PBKDF2 nor a password.
- The program **does not prove** the demo password has production-grade entropy; precisely because the password is hardcoded publicly, it only demonstrates APIs and formats—never use it to protect real data.

### 8.2. Intentional limitations of the program

This is a **standalone Java example**, not a production library. It lacks file persistence, backup/key escrow, key IDs, rotation, tenant isolation, replay defense, identity/authorization, password input UI, and logging/auditing. `PasswordEnvelope` is a record holding mutable arrays, **not an immutable serialized envelope**; production needs defensive copies, a standard parser/serializer, maximum ciphertext length limits, and validated version/algorithm identifiers.

`PBEKeySpec.clearPassword()` clears **the copy** inside the spec. `Arrays.fill(password, '\0')` wipes the caller's array; **it cannot guarantee clearing every copy of the password across the JVM, heap dumps, or libraries**. In demo code, string literals may linger in memory; that is why production must obtain input through secure system mechanisms.

Putting the header in AAD protects version/iterations/salt/nonce bytes upon authentication. Still, before running a CPU-heavy KDF, the receiver must parse the header and **enforce allowlists/cost caps**. When accepting network inputs, add size/rate limits to mitigate DoS. Never silently change AAD encoding across versions; for example, `ByteBuffer` uses big-endian byte order by default and illustrates just one internal layout.

The program generates a random key without **persisting it**; once the JVM exits, there is no way to decrypt that random-key ciphertext without real key management. With PBE, the key can be recreated from password + parameters; with a random key, there must be a secure place to hold/wrap it.

## 9. When to choose which approach?

### Scenario A – a user locks a backup file to open offline

**PBE with a strong password** makes sense if the user must hold the secret themselves and avoid relying on a key server. Store salt, work factor, nonce, ciphertext/tag, and version; define clear reset/recovery expectations. If the password is forgotten and no recovery key exists, the system cannot “recover” it from salt/ciphertext alone.

For large files or frequent password changes, consider a **random DEK + password-derived KEK** so only the DEK is rewrapped instead of re-encrypting gigabytes. That model remains vulnerable to offline password guessing if an attacker obtains the wrapped DEK.

### Scenario B – a backend encrypts customer data fields

Prefer a **random DEK**, typically via envelope encryption with a KMS/HSM. Services grant DEK access by tenant/record, log audits, and restrict service-account permissions. A single shared password hardcoded in code/config to “derive keys” usually creates a single point of failure; if it leaks, all related ciphertexts can be decrypted.

### Scenario C – multiple people are authorized to open the same document

If each user holds their own password, a random DEK can be wrapped separately for each recipient using their own KEK/key. Revoking access requires version management and DEK distribution rules; deleting one wrapped key **does not revoke a DEK that a former recipient already retrieved and saved**. Sensitive data requires access review and DEK rotation on revocation events.

### Scenario D – encryption keys for long-lived data

Random keys in a KMS with backup/rotation are usually easier to organize than a password dependent on human memory. However, this introduces dependencies on KMS availability, networking, and backup policies. Test recovery/escrow workflows in practice; losing a key can mean losing data.

### Scenario E – an application managing login passwords

**Never use PBE to store login passwords and decrypt them for comparison.** For authentication, store a password verifier using a dedicated password-hashing/KDF algorithm such as Argon2id, scrypt, or policy-compliant PBKDF2, with a unique salt, cost parameters, and safe verification. There is no need to recover plaintext passwords for login; “forgot password” flows should reset via separate authenticated verification.

PBE serves cases where **plaintext data must be recovered** from a user-supplied secret; password hashing serves cases where **a password must be verified without recovering the original password**.

## 10. Changing passwords, changing KDF cost, and rotating keys

### 10.1. Changing the password in direct PBE

Suppose a file currently uses `keyOld = KDF(oldPassword, oldSalt, oldCost)`. After the user enters the correct old password:

1. Read old metadata; validate configuration and sizes.
2. Derive `keyOld`, verify the GCM tag, and decrypt the data.
3. Generate a fresh salt and cost/KDF version per new policy; derive `keyNew` from the new password.
4. Generate a fresh nonce and re-encrypt the data with AEAD under the new AAD/version.
5. Persist the new version **atomically** with proper recovery/backup handling, clearing temporary sensitive material as feasible.
6. Update active version / retire old material only after confirming migration succeeded.

You cannot just update a password in the UI and “keep the PBE ciphertext as-is,” because the derived key changes.

### 10.2. Rewrapping the DEK in envelope encryption

With `dataCiphertext = Encrypt(DEK, plaintext)` and `wrappedDEK = Wrap(KEK, DEK)`:

1. Authenticate/recover the DEK using the old password/KEK.
2. Generate a fresh salt and new KEK from the new password (or transition to a KMS key per policy).
3. Wrap the same DEK using the new KEK, fresh nonce/key-wrap format, and valid tag.
4. Persist new metadata and wrapped DEK safely, honoring rollback/backup policies.

The main data payload does not need re-encryption when only the DEK protection changes. If **the DEK itself leaked**, rewrapping does not help; rotate the DEK and re-encrypt the protected data.

### 10.3. Upgrading PBKDF2/scrypt/Argon2id

As workloads and hardware evolve, old work factors become inadequate. Versioning lets you decrypt old records with their exact parameters and then re-encrypt or rewrap under new settings. When using Argon2id/scrypt outside the JDK, verify versions, algorithms, and parameters for system compatibility. Never treat merely editing the iteration count in metadata as a complete upgrade.

## 11. Operations, performance, and common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `new SecretKeySpec(password.getBytes(), "AES")` | Password does not match AES key size, or is long yet low-entropy | Use a dedicated password KDF |
| `SHA-256(password)` as an AES key | KDF is too fast, enabling large-scale offline guessing | Use PBKDF2/scrypt/Argon2id per policy |
| Static salt across all users/files | Identical passwords yield identical keys, aiding precomputation | Unique salt generated via CSPRNG |
| Hiding salt as the primary secret | Misguided threat model, neglecting real secrets | Salts are public; protect passwords/keys |
| Omitting KDF parameters | After config changes, old files become undecryptable | Versioned, self-describing envelope |
| Using `Random` for salt/key/nonce | Predictable source, risk of collisions/weak keys | `SecureRandom` or standard crypto engine |
| Reusing AES-GCM nonces under the same key | Can break confidentiality and authentication | Unique nonces per key, bound key usage counts |
| Using AES-CBC without MAC | No integrity protection, padding oracle risk | AEAD, or proper Encrypt-then-MAC in legacy systems |
| Only checking “decrypt threw no exception” | Can accept tampered data in unauthenticated modes | Use AEAD tag/MAC; never process unauthenticated data |
| Setting cost too low | Attackers test huge candidate rates per second | Benchmark and update KDF policy |
| Assuming extreme cost is always better | Self-inflicted latency/CPU DoS, especially in file-opening services | Bound iterations/memory; validate resource policy before KDF |
| Hardcoding passwords or keys in a JAR | Anyone with the artifact/source can extract secrets | Secure input, secret manager/KMS/keystore |
| Logging passwords, raw keys, or decrypted data | Leaks secrets despite sound algorithms | Redact logs, restrict debug dumps and access |
| Using a strong password then storing plaintext beside ciphertext | Password leaks from storage, nullifying PBE | Protect input paths and secret lifecycle |
| Using a random DEK and forgetting to save/backup it | Permanent loss of decryption capability | KMS/wrapped DEK, key escrow/recovery |
| Rewrapping DEK without accounting for leaked old copies | Adversary holding old wrapped key or DEK retains access | Threat-model rotation/re-encryption and backups |
| Treating key possession as authorization | Holder of ciphertext or ID does not automatically hold business rights | Enforce IAM, tenant policies, and read/unwrap permissions independently |

### 11.1. Be careful with timing and errors

KDFs are intentionally slow; in multi-user APIs, never let a client push iterations into the billions or submit unbounded ciphertexts for backend processing. Enforce size limits, KDF allowlists, acceptable cost ranges, rate limiting, and timeouts/resource budgets. With GCM, handle key/nonce/AAD/tag failures by **rejecting the ciphertext**, never returning plaintext or leaking contents. Never turn `wrong password` vs. `bad ciphertext` into oracle messages exposing cryptographic details outside valid flows.

KDFs can consume substantial CPU; if a system must encrypt huge numbers of records, **do not derive a fresh password key for every row/request** when the architecture does not require it. You may derive a KEK when unlocking a vault and use random DEKs for records, depending on your threat model and session lifecycle. Still, caching plaintext keys long-term increases memory-access risk; balance performance and security carefully.

### 11.2. Java APIs to remember

| API | Purpose | Notes |
| --- | --- | --- |
| `PBEKeySpec` | Holds password `char[]` + salt + iterations + key length | Has `clearPassword()` for the spec's internal copy |
| `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` | Derives key from password | Not an AES cipher or a memory-hard KDF |
| `SecretKeySpec` | Wraps raw derived bytes as an AES key | Clear intermediate buffers appropriately; never log |
| `KeyGenerator.getInstance("AES")` | Generates random AES key via provider | Distinct from password derivation |
| `SecureRandom` | Safely generates salt/nonce/key material | Never use `Random` for secrets |
| `Cipher.getInstance("AES/GCM/NoPadding")` | AEAD encryption/decryption | Nonce unique per key; tag verified on decryption |
| `GCMParameterSpec(128, nonce)` | Tag length and nonce for AES-GCM | 12-byte nonce is standard; 128-bit tag |
| `Cipher.updateAAD(...)` | Authenticates metadata outside plaintext | Must provide AAD before ciphertext data |
| `AEADBadTagException` | Signals AEAD decryption authentication failure | Reject entire ciphertext; never use plaintext |

**Password interoperability note:** `char[]` in `PBEKeySpec` does not guarantee all systems share the same Unicode normalization/encoding. When interoperating between Java and other libraries/languages, explicitly specify password-to-byte conversion, Unicode normalization, KDF variant, and test vectors. A Vietnamese password with diacritics can derive a different key if two systems preprocess Unicode differently. Never convert passwords into extra `String` copies just to “encode easily.”

## 12. Self-check questions

**1. Does PBKDF2 producing 256 bits make a 6-digit password as strong as a random AES-256 key?**  
No. The output is 256 bits, yet the password search space can still be enumerated offline. Work factors slow each guess; they add no entropy to the password.

**2. Can PBE be decrypted if the salt is not stored?**  
Normally you cannot re-derive the exact key without the original salt, unless another key/metadata copy exists. Store the salt alongside format/version/cost and ciphertext.

**3. Are salt and nonce the same thing?**  
No. Salt goes into the KDF; nonce goes into AES-GCM. Both are typically non-secret, yet follow separate rules—in particular, a GCM nonce must never repeat when encrypting under the same key.

**4. Does a randomly generated AES key still need PBKDF2?**  
No PBKDF2 is needed to *generate* a raw random key. If you want to **wrap** a DEK with a password, a KDF can derive a KEK at a separate layer.

**5. Why must PBE use AEAD?**  
Not only to hide plaintext, but also to detect tampered data. Even with the right password, modified ciphertext must be rejected.

**6. Is data safe from offline password guessing just because the server limits logins to 5 attempts?**  
No. Anyone holding the ciphertext can test candidates offline; you still need a strong password and properly configured KDF.

**7. Does envelope encryption eliminate the need to trust a strong password?**  
Not when the KEK is derived from a password. It primarily separates the DEK from the KEK, easing rewrapping/rotation and access sharing.

**8. When changing the password in an envelope, must the data ciphertext always be re-encrypted?**  
No, you can rewrap the DEK. However, if the old DEK or `wrappedDEK` leaked, assess rotation/re-encryption according to the compromise scope.

**9. For a backend system encrypting its own data, how should keys be held?**  
Usually via random DEKs with wrapped keys/KMS or HSM plus IAM/auditing/recovery—never a shared password hardcoded in source.

**10. Is PBE the best way to store login passwords?**  
No. Login passwords should store a hashed verifier via an appropriate password-hashing algorithm, never reversible encryption solely for password comparison.

## References

- [NIST SP 800-132 – Recommendation for Password-Based Key Derivation: Storage Applications](https://csrc.nist.gov/pubs/sp/800/132/final): foundations of password-derived master keys, salts, and iteration counts.
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): choosing Argon2id/scrypt/PBKDF2, password guessing costs, and hashing vs. encryption differences.
- [Java SE 17 – PBEKeySpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html): `char[]` password model, salt, iterations, key length, and `clearPassword()`.
- [Java SE 17 – SecretKeyFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html): creating a `SecretKey` from a `KeySpec`.
- [Java SE 17 – Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): PBKDF2, AES, PBE schemes, and Java algorithm names.
- [Java SE 17 – Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `AES/GCM/NoPadding`, `updateAAD`, authentication tags, and nonce uniqueness.
- [Java SE 17 – KeyGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html) and [SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): generating random keys and provider entropy sources.