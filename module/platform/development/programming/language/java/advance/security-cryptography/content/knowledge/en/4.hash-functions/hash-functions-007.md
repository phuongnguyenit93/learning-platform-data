# 4.7 Limitations of Public Digests Against Replaced Data and Weak Passwords

A **public digest** such as SHA-256 is very useful for detecting altered data **when the verifier already holds a trusted digest value**. However, a hash function contains no secret: anyone who has the data can recompute the digest. Consequently, if an attacker can replace **both the content and the accompanying digest**, the comparison will still succeed. Similarly, directly hashing a predictable password with SHA-256 does not make that password hard to guess: once the digest leaks, an adversary can test huge numbers of candidates **offline** without sending login requests.

These two scenarios both involve hash functions yet have **different threat models**:

- **Data integrity / origin authentication:** the verifier needs to know where the reference digest came from and how it was protected. When origin authentication is needed, use **HMAC** with a shared secret key or **digital signatures** with a trusted public key, depending on the architecture.
- **Password storage and verification:** the server needs to verify a password without storing plaintext, while making every guess against a leaked record expensive in resources. Use a **salted password-hashing/KDF function with a work factor**, preferring Argon2id when a suitable library is available; PBKDF2-HMAC-SHA256 is an example achievable through JCA/JCE APIs in Java.

This lesson pinpoints the exact limitations of digests, illustrates both attacks at a conceptual level, and builds appropriate checks using Java 17+.

## 1. What Does a Public Digest Actually Guarantee?

With `SHA-256`:

```text
Original data (bytes)  ── SHA-256 ──>  256-bit digest (32 bytes)

Verifier:
  recomputedDigest = SHA-256(receivedData)
  recomputedDigest == referenceDigest ? "match" : "mismatch"
```

SHA-256 is a cryptographic hash function designed with security properties such as preimage resistance, second-preimage resistance, and collision resistance. Its output has fixed length; changing a single byte of data normally changes the digest. However, **it is not a publisher authentication mechanism**. A hash function is a public, unkeyed algorithm, so an adversary can equally compute `SHA-256(forgedContent)`.

Distinguish common terms:

| Concept | Question answered | Limitation to remember |
| --- | --- | --- |
| **Digest match** | Does the data on hand match the **reference value used for comparison**? | Does not prove that the reference value itself is trustworthy. |
| **Collision resistance** | Is it hard to find two distinct messages with the same digest? | An attacker replacing both content and digest **does not need to find a collision**. |
| **Preimage resistance** | Is it hard to find input data from a digest for a sufficiently unpredictable input? | Short/common passwords have a small search space; dictionary guessing works. |
| **Integrity with a trusted source** | Does the current data match content published by an authenticated source? | Depends on how the reference digest is protected or sourced. |
| **Origin authentication** | Was the data genuinely produced by a party holding a valid key? | Requires MAC/digital signatures and key management; a plain digest is insufficient. |

A SHA-256 checksum posted on an official page can be useful if the page/channel serving the checksum is itself authenticated and cannot be altered by an adversary. If both the file and checksum are fetched from **the same untrusted HTTP repository** controlled by an adversary, matching the checksum offers virtually no proof against tampering.

### 1.1 Attack Replacing Both Data and Digest

```text
PUBLISHER                   MUTABLE CHANNEL                    RECEIVER
file.bin  ----------------> [replaced with fake.bin] --------> fake.bin
SHA256(file.bin) ----------> [changed to SHA256(fake.bin)] --> SHA256(fake.bin)

Receiver: SHA256(fake.bin) == SHA256(fake.bin)  => true
Receiver: has no idea what the original file.bin was!
```

The attacker does not break SHA-256, does not invert the algorithm, and does not need to find two files sharing a digest. They simply swap in **a matching pair of data + digest**. If the receiver has the original digest verified from an independent channel, comparing against the forged pair will **fail to match**.

Therefore, ask the right questions: *"Who is allowed to change the content? Who is allowed to change the reference digest? On what basis do we trust the reference digest?"* Answer these three questions before claiming a checksum "protects integrity."

### 1.2 When Is SHA-256 Alone Appropriate?

- **Detecting accidental transmission/storage corruption:** e.g., checksums of backups or build artifacts, when the initial reference point is trusted.
- **Content identification (content addressing/deduplication):** using digests to index content; additional source/expected-value controls are needed when an active adversary exists.
- **Download verification:** checking that a file's digest matches an official digest obtained via a trusted channel. A digest fetched from the same unprotected source does not prove the publisher.
- **Not appropriate alone:** authenticating webhooks, ensuring update manifests are not swapped, signing software packages, protecting data against an attacker who can modify both data and checksum, or protecting databases of weak passwords.

## 2. Three Ways to Protect Data Against Substitution

When defending against an adversary who can alter data, choose the mechanism based on who needs to verify and who holds the keys.

| Mechanism | Secret / trust anchor to maintain | Who can verify? | Used for |
| --- | --- | --- | --- |
| `SHA-256(data)` and **authenticated expected digest** | The channel/manifest holding the reference digest must be trusted | Anyone with the trusted expected digest | Verifying file downloads, release checksums. |
| `HMAC-SHA256(key, data)` | **Symmetric secret key** shared only among authorized parties | Parties holding the same key | Authenticating internal webhooks or messages between two key-sharing services. |
| **Digital signature** `Sign(privateKey, data)` | Signer's private key; their identity and public key must be authenticated | Anyone with a **trusted public key** | Software distribution, release manifests, independent verification by many parties. |
| **AEAD** (e.g., AES-GCM) | Valid encryption key, proper nonce/IV discipline, and tag | Parties holding the decryption key | When both **content confidentiality and ciphertext authentication** are needed, not just a checksum. |

**HMAC** uses a hash function internally together with a **secret key**, so a party that alters data without knowing the key cannot generate a valid MAC. Do not use a homemade `SHA256(key || message)` instead of HMAC; use `javax.crypto.Mac` and `HmacSHA256`. HMAC keys must be sufficiently random, provisioned and managed securely, and never hardcoded. Any party knowing the same key can also generate a MAC, so HMAC does not provide public non-repudiation of who signed as digital signatures do.

For digital signatures, the Java API is `java.security.Signature`. The publisher signs with `PrivateKey`, and recipients verify with a `PublicKey` **bound to a trusted identity**. Fetching a public key from the same compromised repository without verifying its origin can still result in verifying a forged signature made with an adversary's key. When using certificates, validate the trust chain, key usage, and revocation/validity status per policy.

HMAC/digital signatures also **do not automatically prevent replaying** an older valid message. If the system must prevent replay/rollback, include version, timestamp, sequence/nonce, or event ID in the authenticated data and enforce state checks on the receiving side.

## 3. Java 17+ Example: Replacing Data, Replacing Digest, Comparing HMAC, and Guessing a Weak Password

Save as **`PublicDigestDemo.java`**. The example uses `MessageDigest` for SHA-256 and `Mac` for HMAC-SHA256. The password-guessing block runs only on a sample `123456` created inside the program to explain the offline attack mechanism.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class PublicDigestDemo {
    static byte[] sha256(String text) throws GeneralSecurityException {
        return MessageDigest.getInstance("SHA-256")
                .digest(text.getBytes(StandardCharsets.UTF_8));
    }

    static byte[] hmac(String text, byte[] key) throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(text.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws GeneralSecurityException {
        String original = "name=invoice;amount=100";
        String changed = "name=invoice;amount=900";

        byte[] trustedDigest = sha256(original);
        byte[] replacedDigest = sha256(changed);

        // Attacker replaces only the file; the original expected digest is protected.
        System.out.println("1. Old digest matches modified content: "
                + MessageDigest.isEqual(trustedDigest, sha256(changed)));

        // Attacker replaces both the file and the accompanying expected digest.
        System.out.println("2. Forged digest matches modified content: "
                + MessageDigest.isEqual(replacedDigest, sha256(changed)));

        // Example key generated randomly; legitimate endpoints must share it securely.
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);
        try {
            byte[] trustedMac = hmac(original, key);
            // Receiver recomputes the MAC using its own secret key.
            System.out.println("3. Old HMAC matches modified content: "
                    + MessageDigest.isEqual(trustedMac, hmac(changed, key)));
        } finally {
            Arrays.fill(key, (byte) 0);
        }

        // Illustrates only a self-created weak password; do not use in real handling.
        byte[] leakedDigest = sha256("123456");
        boolean guessed = false;
        for (String candidate : new String[]{"admin", "123456", "welcome"}) {
            if (MessageDigest.isEqual(leakedDigest, sha256(candidate))) {
                guessed = true;
                break;
            }
        }
        System.out.println("4. Weak password guessed offline: " + guessed);
    }
}
```

Run with Java 17+ using a standard JDK provider supporting SHA-256 and HmacSHA256:

```bash
javac -encoding UTF-8 PublicDigestDemo.java
java PublicDigestDemo
```

Stdout (independent of the random key value):

```text
1. Old digest matches modified content: false
2. Forged digest matches modified content: true
3. Old HMAC matches modified content: false
4. Weak password guessed offline: true
```

Read the four outputs carefully:

1. `false`: the forged data's digest **differs** from the trusted original digest. This is the case where checksum comparison is useful.
2. `true`: the forged digest was computed over the forged data, so it matches. This is a **failure of an unprotected reference source**, not a flaw in SHA-256.
3. `false`: the valid MAC of the original message no longer matches the altered message. In practice, an adversary **does not know the key** and therefore cannot simply compute a new valid MAC; the receiver obtains the original MAC from a policy-permitted source and verifies it.
4. `true`: from just a SHA-256 digest of a weak password, the program guesses it using a small candidate list. There is no "hash decryption" operation: it simply **hashes each candidate and compares**.

`MessageDigest.isEqual(byte[], byte[])` is appropriate for comparing digests/MACs at the byte level; avoid homemade string comparisons that exit at the first differing character. Do not confuse "careful comparison" with "preventing brute force": it does not slow down hashing and does not add secrecy to a public digest. The example uses fixed `String`s for readability; real data must be authenticated over **exact byte sequences**, with consistent formatting/canonicalization.

## 4. Why Does Plain SHA-256 Fail to Protect Weak Passwords?

Suppose a database stores:

```text
username = alice
password_hash = SHA256("123456")
```

When the record leaks, the adversary knows the algorithm is SHA-256 and knows the stored digest. They can try millions of candidates from dictionaries/rule sets on their own machines, compute `SHA256(candidate)`, and compare. They are not constrained by login endpoint rate limits, CAPTCHAs, or account lockouts, because this is an **offline attack on leaked data**. Actual throughput depends on hardware and algorithm, yet SHA-256 is designed to run fast; that is great for checksums, and detrimental when passwords have low randomness.

Misconceptions to correct:

- **"SHA-256 is irreversible, so no one can find the password."** No inversion is needed: just test high-probability passwords. A value like `123456` is guessed very quickly.
- **"Switching SHA-256 to SHA-512 is enough."** SHA-512 is also a fast general-purpose digest; merely increasing digest length does not add a substantial work factor.
- **"Hashing twice or a few times is secure."** Looping a few homemade rounds of SHA-256 is not equivalent to analyzed and cost-tuned password hashing.
- **"Adding a salt makes the password hard to guess."** A salt primarily prevents precomputed hash tables and reduces the effectiveness of reusing computations across multiple accounts. A salt **does not increase the true entropy** of the password.
- **"Keeping the algorithm name secret is enough."** Never rely on algorithm secrecy: the design must hold up even if the algorithm, parameters, and salt are exposed.
- **"Having rate limiting makes it safe."** Rate limiting protects **online** access, not offline guessing over leaked hash data.

If a password belongs to a small set, an adversary can test that entire set against any public hash. Passwords must be sufficiently unpredictable, systems should screen out common/breached passwords per policy, and password hashing with substantial cost must be used.

### 4.1 How Do Salt, Work Factor, and Pepper Differ?

```text
password (user secret) + unique salt (public)
                |
                v
 Password KDF (e.g., PBKDF2-HMAC-SHA256)
   with high, calibrated cost / iterations
                |
                v
    derived hash / verifier
                |
                v
Store: algorithm + parameters + salt + derived hash
```

| Component | Role | Can it be stored with the hash? |
| --- | --- | --- |
| **Salt** | Generated uniquely and randomly per record; ensures identical passwords usually yield different outputs; defeats shared precomputed lookup tables. | **Yes.** A salt is not a password and does not need to stay secret. |
| **Work factor** | Makes each guess costlier in CPU and/or RAM; updated over time as hardware evolves. | **Yes.** Must be stored to verify the record and support upgrades. |
| **Pepper** (optional) | An additional secret used in an appropriate design, helping defend against database-only leaks. | **No.** Store separately from the DB, e.g., in a secret manager or HSM; do not embed in source code or the same hash table. |
| **Password** | The secret supplied by the user for verification. | **Never store plaintext** and never write to logs. |

**A salt is not an HMAC key.** A single `SHA256(salt || password)` with a good salt is still a **fast** hash; it is insufficient against offline guessing. Salts must be used **with** a dedicated password KDF. Two users sharing a password should have separate salts and separate hashes, yet a common password remains easier to guess than a strong random passphrase.

**Pepper does not replace salt/KDF**. It is an additional control with operational overhead (key management/rotation, recovery), useful only when the pepper key does not leak alongside the data. If an attacker has write access to the hash table in the database, they can alter records in other ways: slowing down password guessing **does not by itself provide integrity** or database write access control.

## 5. Choosing the Right Password Storage Mechanism

The goal of password hashing is to consume significant resources **for every candidate guess**, even when an attacker possesses the hash/salt record. Commonly used options:

| Mechanism | Characteristics | When to use |
| --- | --- | --- |
| **Argon2id** | Purpose-built password KDF with RAM, time, and parallelism parameters; resists parallel hardware guessing better than fast digests. | **Preferred for new designs** when a trusted library and operational support are available. |
| **scrypt** | Memory-hard KDF with CPU/RAM parameters. | When Argon2id is unavailable yet a trusted scrypt library is available. |
| **bcrypt** | Password hash with tunable cost; many implementations have a 72-byte input length limit. | Legacy systems already using bcrypt; check exact limits and migration. |
| **PBKDF2-HMAC-SHA256** | KDF based on HMAC iteration count; widely supported and usable via `SecretKeyFactory` on suitable JDKs. Not memory-hard. | When compatibility/compliance requires it or for learning JCA/JCE APIs; iteration count must be calibrated. |
| **Plain SHA-256/SHA-512/MD5** | Fast general-purpose digests without built-in password cost/salting. | **Never** use directly as a password verifier. |

Per the **OWASP Password Storage Cheat Sheet** referenced for this lesson, a typical minimum configuration for Argon2id is `m=19456 KiB (~19 MiB), t=2, p=1`; for PBKDF2-HMAC-SHA256 it is **600,000 iterations** (especially when a FIPS-compliant solution is needed). These values are **baseline references at implementation time**; always check current guidance and measure in your production environment. Raising cost excessively can overload servers during login spikes; combine with traffic limits and capacity sizing. Never rely on a single laptop benchmark for every environment.

Java 17 provides `javax.crypto.SecretKeyFactory` and `javax.crypto.spec.PBEKeySpec` for PBKDF2 via providers supporting `PBKDF2WithHmacSHA256`. The standard JDK does not expose a built-in API guaranteed to offer Argon2id across all environments: if choosing Argon2id, use a maintained library, verify versions/dependencies, and follow the library's guidance.

### 5.1 Rules for Storing Verifier Records

A record should contain enough information **to verify and upgrade**, for example:

```text
pbkdf2-sha256$600000$base64(salt)$base64(derivedHash)
```

This is a **custom format for the example**; the fields are scheme name, iteration count, salt, and derived hash. Every field except the password may be public. In production, define stable encoding and format versioning, enforce acceptable bounds on lengths and costs so malformed records cannot trigger DoS, apply migrations for legacy records, and protect write permissions/integrity of the store. Never store passwords in Base64: Base64 is merely a representation encoding.

## 6. Java 17+ Example: Storing and Verifying Passwords with Salted PBKDF2

This example uses **PBKDF2WithHmacSHA256**, a 16-byte salt from `SecureRandom`, **600,000** iterations, and a 256-bit output. Algorithm name/salt/cost are stored with the verifier; upon verification, the stored salt/cost are reused and compared with `MessageDigest.isEqual`. The password in `main` is a public illustrative value—**never** use it as a real password.

Save as **`PasswordStorageDemo.java`**:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordStorageDemo {
    private static final String SCHEME = "pbkdf2-sha256";
    private static final String JCA_ALGORITHM = "PBKDF2WithHmacSHA256";
    private static final int ROUNDS = 600_000;
    private static final int SALT_BYTES = 16;
    private static final int KEY_BITS = 256;
    private static final SecureRandom RANDOM = new SecureRandom();

    private static byte[] derive(char[] password, byte[] salt, int rounds)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, rounds, KEY_BITS);
        try {
            return SecretKeyFactory.getInstance(JCA_ALGORITHM)
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static String store(char[] password) throws GeneralSecurityException {
        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);
        byte[] result = derive(password, salt, ROUNDS);
        try {
            return SCHEME + "$" + ROUNDS + "$"
                    + Base64.getEncoder().encodeToString(salt) + "$"
                    + Base64.getEncoder().encodeToString(result);
        } finally {
            Arrays.fill(result, (byte) 0);
        }
    }

    static boolean verify(char[] input, String record)
            throws GeneralSecurityException {
        if (record == null) return false;
        String[] fields = record.split("\\$", -1);
        if (fields.length != 4 || !SCHEME.equals(fields[0])) return false;

        int rounds;
        try {
            rounds = Integer.parseInt(fields[1]);
        } catch (NumberFormatException ex) {
            return false;
        }
        // Reject abnormal cost values in the demo format produced by this application.
        if (rounds < 100_000 || rounds > 2_000_000) return false;

        byte[] salt;
        byte[] expected;
        try {
            salt = Base64.getDecoder().decode(fields[2]);
            expected = Base64.getDecoder().decode(fields[3]);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        if (salt.length != SALT_BYTES || expected.length != KEY_BITS / 8) {
            return false;
        }

        byte[] actual = derive(input, salt, rounds);
        try {
            return MessageDigest.isEqual(expected, actual);
        } finally {
            Arrays.fill(actual, (byte) 0);
        }
    }

    public static void main(String[] args) throws GeneralSecurityException {
        char[] good = "DemoOnly#NotARealPassword".toCharArray();
        char[] wrong = "wrong-guess".toCharArray();
        try {
            String record = store(good);
            System.out.println("4. Correct password: " + verify(good, record));
            System.out.println("5. Wrong password: " + verify(wrong, record));
            String[] fields = record.split("\\$");
            System.out.println("6. 16-byte salt stored: "
                    + (Base64.getDecoder().decode(fields[2]).length == 16));
        } finally {
            Arrays.fill(good, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
```

```bash
javac -encoding UTF-8 PasswordStorageDemo.java
java PasswordStorageDemo
```

Stdout (the salt and hash on each run are random, yet the verification lines below are deterministic):

```text
4. Correct password: true
5. Wrong password: false
6. 16-byte salt stored: true
```

Step-by-step explanation:

1. `store` generates a **fresh salt** for each record using `SecureRandom`, never reusing a single fixed salt.
2. `PBEKeySpec(password, salt, rounds, KEY_BITS)` specifies the PBKDF2 parameters; `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` computes the derived key. Never replace this with a homemade loop of a few `MessageDigest.getInstance("SHA-256")` calls.
3. `SCHEME` and `rounds` are stored so old and new records can later be distinguished. The salt must match the one used when creating the record; **never generate a new salt during verification**.
4. `verify` validates the format, round bounds, salt length, and hash length before recomputing. Bounding `rounds` in the example prevents abnormal record parameters from tying up the CPU for too long; real systems must define a migration policy for historical values.
5. `MessageDigest.isEqual` compares the derived byte arrays; never use `String.equals` on plaintext or compare character by character until mismatch.
6. `PBEKeySpec.clearPassword()` clears the **password copy inside the spec**, and `Arrays.fill` zeroes several buffers owned by the program. This does not guarantee clearing every copy inside the JVM or provider. Because `main` uses a public string literal for demonstration, never accept production passwords that way; collect input through a secure flow and avoid keeping/logging it as a long-lived `String`.

**Limitations of this example:** this is a console Java module for learning JCA/JCE, without a database, login API, TLS, rate limiting, pepper, breached-password checking, migration, or load monitoring. Records that an attacker can **modify directly** still require database write-access/integrity controls. `PBKDF2` slows down offline guessing, yet cannot compensate for an extremely weak password and does not replace account management workflows.

## 7. Operating Password Verifiers in Production

A practical design considers password hashing across its entire lifecycle:

1. **Registration / password change:** enforce policies on length, common/breached passwords, and Unicode support; avoid arbitrary character-composition rules. NIST SP 800-63B-4 emphasizes length, blocklists, sufficiently strong passwords, and password-manager compatibility.
2. **Consistent normalization:** the exact same password must enter the KDF under identical encoding/Unicode rules at creation and verification. If Unicode normalization such as NFC is applied, put it in the contract and apply it consistently. Never silently `trim`, lowercase, or truncate passwords during verification.
3. **Verifier creation:** use the KDF, a fresh salt, and a configured, measured work factor. Never let clients control the algorithm/cost via requests; never generate salts from `Random` or system timestamps.
4. **Structured storage:** record algorithm/version, salt, cost, and derived hash. Enforce proper DB permissions, backups, and logging; never store plaintext or recovery hints.
5. **Verification:** receive passwords over TLS or an equivalent protected channel; use stored parameters, compare safely, and return failure messages that do not leak account internals. Rate limiting and abuse protection remain essential even with a KDF.
6. **Upgrading:** when cost or scheme is outdated, **right after a valid verification** you can generate a new verifier with a fresh salt/cost and update it safely. You cannot directly convert a legacy SHA-256 hash into an equivalent strong password KDF without the original password; plan a rehash-on-login or reset flow.
7. **Monitoring and incident response:** track verification latency/capacity, detect credential stuffing and account attacks, protect any separate pepper, and force password resets upon evidence of secret exposure.

### 7.1 Measuring Cost and Preventing Overload

Password hashing is intentionally resource-intensive. If each verification consumes significant CPU/RAM, high concurrency can exhaust service resources. Combine a calibrated work factor, attempt limits, concurrency controls, timeouts, and latency monitoring. With Argon2id in particular, calculate total RAM across concurrent requests rather than blindly raising `m` to the maximum value in reference docs.

**Never silently lower the work factor** just because the system is overloaded. Profile real traffic, optimize the verification pipeline, set concurrency limits, choose an approved configuration, and re-measure whenever hardware/JDK/provider changes.

## 8. Choosing the Right Mechanism Across Scenarios

| Scenario | What to choose? | Why? |
| --- | --- | --- |
| Want to know if a downloaded file matches the exact bytes of a **verified** checksum | SHA-256 + trusted expected digest | Verifies byte match; no new key is needed when the expected source is already authenticated. |
| File and checksum sit in the same repository an adversary could alter | Digital signature on the manifest/file or digest from an independently protected source | A plain digest of a forged file still matches a forged digest. |
| Two services use a shared secret to authenticate webhook payloads | HMAC-SHA256 with key management and clear authentication formatting | Parties without the key cannot forge a valid new MAC. |
| Public download verified independently by many parties | Digital signature and public key bound to a trusted identity | Avoids sharing a secret HMAC key with every user. |
| Need both confidentiality and ciphertext authentication | Appropriate AEAD, e.g., AES-GCM | Digests/MACs do not encrypt to hide plaintext. |
| Storing login verifiers | Argon2id/scrypt or suitable PBKDF2 + unique salt + cost | Slows offline guessing attacks on potentially leaked passwords. |
| User picks `123456` | Blocklist/password policy, strong passwords, KDF, and additional auth controls | A KDF cannot turn an easily guessed secret into a strong one. |
| Adversary has write access to the password verifier table | Protect DB write permissions, integrity checks, and change monitoring | KDF resists password guessing on leaked records; it does not stop record replacement itself. |

### 8.1 Four Questions for Self-Checking

**Question 1.** "I downloaded a file from server A, and server A also returned a SHA-256. The two values match; am I sure the file was not swapped?"  
**Answer:** You are only sure the file matches the checksum you received. If an adversary can alter both in transit or storage, there is no origin guarantee. You need channel authentication, a trusted expected checksum, or a digital signature.

**Question 2.** "If an attacker replaces both the file and checksum and they still match, did SHA-256 suffer a collision?"  
**Answer:** No. The adversary computed a new digest for the new file; they did not need two distinct files with the same digest. Collisions are unrelated to this scenario.

**Question 3.** "Is adding a 16-byte random salt to `SHA256(password)` enough for password storage?"  
**Answer:** No. A salt differentiates hashes across records and defeats precomputed tables, yet single-round SHA-256 remains fast. Use a dedicated KDF with a work factor, per-record salt, and strong passwords.

**Question 4.** "In the PBKDF2 program, why must verification read the salt and rounds from the record?"  
**Answer:** The KDF must receive the exact parameters used when creating the verifier; a new salt would yield a different output. Storing version/work factor allows verifying historical records and upgrading over time.

**Question 5.** "Should we hide the name `PBKDF2WithHmacSHA256` or the salt value to prevent password exposure?"  
**Answer:** No need. They are treated as public information. Security relies on unpredictable passwords, a properly chosen/calibrated KDF, and protections for auxiliary secrets/data.

**Question 6.** "I use HMAC for webhooks. If a valid old payload is replayed identically, will HMAC block it?"  
**Answer:** No. The MAC remains valid on the old message. If replay is harmful, sign/authenticate a timestamp, message ID, or sequence number as well and check time windows/deduplication on the receiver.

## 9. Common Mistakes

- Checking `SHA256(file)` against a digest in the same untrusted response and concluding the file was created by the true publisher.
- Thinking an attack replacing `file + digest` requires finding a SHA-256 collision; in fact, it only requires computing the digest of the forged data.
- Using `MessageDigest` directly as a password hash or looping a few homemade rounds and treating it as a password-storage KDF.
- Using one static salt for all users; deriving the salt from username, timestamp, or predictable sources; or treating the salt as a secret to hide.
- Assuming salt/pepper/MFA/rate limiting can substitute for one another. They address different threat layers.
- Using homemade `SHA256(key || message)` instead of HMAC; failing to protect keys, manage key rotation, or control replay.
- Using digital signatures yet downloading an unauthenticated public key from the same untrusted source as the file being checked.
- Storing plaintext passwords, logging passwords, treating Base64 as security, or keeping hardcoded test credentials in production.
- Creating PBKDF2 records without storing salt/work factor/version; trying to verify with a new salt; omitting malformed-data or excessive-cost checks.
- Allowing weak/compromised passwords into the system and hoping a strong KDF will offset every risk.

## 10. Pre-Deployment Checklist

**For files/messages:** identify who can alter content and digests; choose a trusted expected digest, HMAC, or digital signature; authenticate the trust anchor; verify exact bytes/encoding and format; add replay/rollback protection if needed.

**For passwords:** never store plaintext; screen weak passwords per policy; use a vetted KDF; generate unique salts; calibrate cost; store schema/version/salt/cost/hash; compare safely; rate-limit online attempts; restrict DB write permissions; design upgrades/migration and protect any pepper.

## Reference Materials

- [Java SE 21 — MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html): computing digests, `digest`, `isEqual`.
- [Java SE 21 — Mac](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html): HMAC, `init`, and `doFinal`.
- [Java SE 21 — Signature](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html): signing and verifying digital signatures.
- [Java SE 21 — SecretKeyFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/SecretKeyFactory.html) and [PBEKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html): generating PBKDF2 verifiers with salt and iteration count.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): Argon2id, scrypt, bcrypt, PBKDF2, salt, pepper, work factor, migration.
- [NIST SP 800-63B-4 — Password verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html#verifierreq): protecting password verifiers against offline attacks, salt, cost, and adjusting over time.
- [OWASP — Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): choosing cryptographic mechanisms based on threat models.

**Key takeaway:** a public digest is useful for **comparing against a trusted expected value**; it does not authenticate the author when both data and digest can be replaced. For origin authentication, use HMAC/digital signatures with proper key management. To protect weak passwords from offline guessing, use salted, cost-tuned password hashing—while still encouraging sufficiently strong passwords.
