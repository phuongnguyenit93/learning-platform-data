# 7.3 Roles of Salt, Iteration Count, Output Length, and Configuration Version

When storing passwords or deriving keys from passwords in Java, you commonly encounter the parameters **salt**, **iteration count**, **derived key length**, and **configuration version**. They answer four distinct questions:

1. **Salt:** do two operations on the same password produce the same output, and can precomputed tables or attack work be shared across multiple accounts?
2. **Iteration count / cost:** how much computational work does a single password-guessing attempt require?
3. **Output length:** how many bits/bytes are in the binary result for comparison or use as key material?
4. **Configuration version:** how do you know which algorithm and parameters produced an old result, verify it, and safely upgrade it when policy changes?

The four parameters **do not substitute for one another**. A salt does not make a weak password hard to guess; increasing output from 256 to 512 bits does not increase password entropy; the iteration count must be calibrated to hardware and operational needs; and configuration versioning lets the system migrate from old policies to new ones.

This lesson belongs to **passwords and key derivation**. Distinguish two goals: **password hashing for login verification** and **password-based key derivation for creating encryption keys**. Both may use a KDF, yet their lifecycles and result storage differ.

## 1. Conceptual framework: password, KDF, and verifier

A password-based key derivation function generally has the abstract form:

```text
derived = KDF(password, salt, cost_parameters, output_length, algorithm)
```

For **PBKDF2-HMAC-SHA256**, the model can be written:

```text
DK = PBKDF2-HMAC-SHA256(P, S, c, dkLen)
P      = password
S      = salt
c      = iteration count
dkLen  = desired output length (bytes per PBKDF2 specification)
DK     = derived key (resulting bytes)
```

In Java, `PBEKeySpec(char[] password, byte[] salt, int iterationCount, int keyLength)` takes `keyLength` **in bits**, unlike the `dkLen` notation **in bytes** in the PBKDF2 specification. Thus **256** in `PBEKeySpec(..., 256)` targets an output of **256 bits = 32 bytes**, not 256 bytes.

**KDF** is a broad family; each variant has its own cost parameters:

| Algorithm | Primary cost parameter(s) | Properties | Where commonly seen |
| --- | --- | --- | --- |
| **PBKDF2-HMAC-SHA256** | `iterations` | Increases CPU cost by iteration count | Java JCA/JCE, systems requiring PBKDF2 |
| **Argon2id** | `memory`, `time cost`, `parallelism` | Memory-hard, raises cost of parallel/GPU attacks | Systems with a trusted Argon2id library |
| **scrypt** | `N`, `r`, `p` | Memory-hard with resource parameters | Certain password hashing/KDF systems |
| **bcrypt** | Cost factor (logarithmic) | Dedicated cost mechanism with input limits to watch | Password verifiers in legacy/existing applications |

You cannot directly compare “PBKDF2 200,000 iterations” with “Argon2id 3 passes” or “bcrypt cost 12”: they measure **different kinds of work**. Choose the algorithm and configuration based on your threat model, server resources, and current security guidance, then **measure on real hardware**.

### 1.1. Password hashing differs from decryptable encryption

To **verify login**, the backend stores a **verifier** derived from the password, not the original password or ciphertext decryptable by an application key. When the user logs in, the backend retrieves the *stored salt and parameters*, recomputes the KDF for the entered password, and compares the result. It never needs the original password.

To **derive an encryption key from a password**, the output can serve as key material for AES or another mechanism. When the password and parameters are re-entered correctly, the KDF returns the same key bytes to unlock the data. This case also requires managing IV/nonce, authenticated encryption, password changes, data recovery, and parameter stability. Do not assume the same KDF output may be reused simultaneously as a verifier, AES key, and HMAC key: separate purposes need **separate keys or domain-separated derivation**.

### 1.2. Components that must be stored with the result

In a password verification system, a minimal record usually includes **algorithm identifier**, **cost parameters**, **salt**, **output length/format**, **derived digest**, and **configuration version**. None of these fields contain the plaintext password.

Example record layout (field names describe structure, not a precomputed verifier string):

```text
CredentialRecord
  formatVersion      : 2
  algorithm          : PBKDF2WithHmacSHA256
  iterations         : 180000
  derivedKeyBits     : 256
  salt               : binary, 16 bytes (stored as Base64URL)
  verifier           : binary, 32 bytes (stored as Base64URL)
```

**180,000 iterations in this example is solely an illustrative value for the upgrade flow, not a production configuration recommendation.** In real systems, check policy requirements and benchmark at deployment time.

## 2. Salt: a unique random value for every verifier creation

A **salt** is extra input data passed to the KDF. For a given password, changing the salt changes the derived output in cryptographic practice:

```text
KDF("example-password", salt_A, params) != KDF("example-password", salt_B, params)
```

Two accounts using the same password **must not share the same verifier**. If they have sufficiently long, independently generated random salts, the KDF outputs are almost certainly different. This prevents spotting duplicate passwords merely by comparing hashes and forces an attacker to perform password guessing separately for each salt rather than reusing work precomputed for a shared salt.

### 2.1. Why is a salt required?

- **Defeats precomputed lookup tables:** rainbow tables/lookup tables for unsalted hashes do not apply directly across independent salts.
- **Prevents mass identical verifiers:** two users picking the same password get different verifiers when their salts differ.
- **Limits attack-cost sharing across targets:** an attacker must evaluate each record's specific salt.
- **Preserves verifiability:** storing the salt in the record allows the backend to recompute the exact same KDF on future logins.

A salt **does not stop** an attacker from guessing a specific password offline once they obtain both the verifier and the salt. Nor does a salt add entropy to the password. A weak password remains relatively easy to guess when using a cheap KDF or unlimited trials.

### 2.2. Salt must be random, independent, and sufficiently long

For new systems, a straightforward practical example is **16 bytes (128 bits) of salt generated by `SecureRandom`** per verifier. Some algorithms/formats have specific requirements; follow the specification of the algorithm, library, or storage format in use.

```java
byte[] salt = new byte[16];
new java.security.SecureRandom().nextBytes(salt);
```

This snippet is illustrative, not a standalone program. **Generate a fresh salt whenever creating a new verifier**, even when two users choose the same password. When upgrading configuration via rehash on login, generate a **fresh salt** for the new record.

Avoid using one global salt for all accounts, using username/email as a salt, deriving salt solely from timestamps or predictable counters, or generating salts with a non-cryptographic RNG like `Random`. Identity data can be part of a protocol structure, but **cannot replace a random salt** where randomness is required.

With a 128-bit random salt, collision probability between two independent salts is negligible at normal scale. Still, the decisive factors are **using a cryptographic RNG and generating a fresh salt per operation**, not just array length.

### 2.3. Is a salt secret?

**No. A salt is typically stored publicly alongside the verifier** in the database. The verifier check must read the exact salt to reproduce the output. Security relies on a hard-to-guess password and an adequately costly KDF, **not on hiding the salt**.

- **Salt:** non-secret, per-record, used to diversify outputs.
- **Pepper (if used):** a shared or scoped secret kept outside the DB, e.g., in a KMS/HSM/secret manager. Pepper cannot replace a salt; adding and rotating a pepper requires dedicated algorithm/rotation design.
- **Nonce/IV:** plays a different role in encryption protocols; not synonymous with salt.
- **Secret key:** a key that must stay confidential; never turn a salt into a secret or use a salt as an AES/HMAC key.

If a record is copied to another environment without its salt, re-verification may become **impossible**, because KDF output depends strictly on the salt.

### 2.4. Different salts vs. altered salts

With the same password, same algorithm, and same iteration count:

```text
KDF(P, S1, 100000, 32 bytes) -> output_1
KDF(P, S2, 100000, 32 bytes) -> output_2
```

`output_1` and `output_2` differ because `S1 != S2`. If the backend accidentally generates a new salt every time a user *logs in* instead of using the stored salt, verification **will fail**. A new salt is generated only when creating a new verifier or during a controlled rehash.

Do not treat “a 16-byte salt” as sufficient proof of security: you must know **how it was generated**, whether it is reused at scale, and whether its exact bytes are stored and read intact.

## 3. Iteration count: tuning the cost of password guessing

In PBKDF2, `iterationCount` is the number of rounds the internal PRF chain executes. Holding other factors constant, raising the iteration count increases CPU and time per derivation. This helps because an offline attacker typically needs to test vast numbers of password guesses.

However, **high cost affects legitimate operations too**: logins, password resets, batch migrations, and data unlocks all consume more CPU, potentially causing bottlenecks or enabling DoS if unthrottled.

### 3.1. Why not use a fast hash for password storage?

SHA-256 is a fast hash designed to process data efficiently. If a system stores `SHA256(password)` or only `SHA256(salt || password)`, an attacker who obtains the verifier database can test huge numbers of passwords very rapidly.

A password KDF adds **intentional computational cost**. With PBKDF2, every trial runs the configured number of rounds. With Argon2id/scrypt, the goal can also include memory cost, making parallel attacks on GPUs/ASICs harder to optimize.

**Adding a salt to SHA-256 does not replace PBKDF2/Argon2id/scrypt** as a properly costed password KDF.

### 3.2. Choosing iteration counts via policy and benchmarking

A production configuration should be decided step by step:

1. Select a supported KDF algorithm evaluated as suitable for your threat model and compatibility/compliance requirements.
2. Consult security guidance **current at deployment time**. What counts as “good” iterations shifts with hardware and algorithmic improvements.
3. Measure **p50/p95/p99** verification latency on realistic target hardware/instances under concurrent load.
4. Set a latency/CPU budget and defend against brute force/DoS; consider quotas, rate limits, MFA, and capping concurrent verification requests.
5. Record the approved configuration in a version/policy, monitor performance, and plan cost increases across upgrades.

**Do not use the demo values of 100,000 or 180,000 iterations in the Java example below as production recommendations.** They only illustrate keeping an old configuration, verifying it, and migrating to a new one.

### 3.3. How does increasing iterations affect performance?

If PBKDF2 at 100,000 iterations takes roughly 50 ms on a machine, 200,000 iterations will **typically** nearly double the KDF CPU work under the same conditions. This is a **directional trend**, not a real-time guarantee; provider, JVM, CPU, load, caches, and environment all affect benchmarks.

Attackers can still optimize hardware, parallelize, and guess weak passwords. Iteration counts **do not create** higher password entropy. Therefore you still need strong passwords/passphrases, MFA where appropriate, and protection on online guessing endpoints.

### 3.4. Argon2id and bcrypt do not use “rounds” in the same way

- **Argon2id:** cost parameters typically include memory (e.g., KiB), pass count/time cost, and parallelism. Evaluate **all three together**, not just a single word “iterations”. Argon2id also has an algorithm version parameter; configuration must include the full parameter set.
- **scrypt:** uses `N`, `r`, and `p` parameters tied to work and memory; `N` cannot be compared directly to PBKDF2 rounds.
- **bcrypt:** its cost factor scales work exponentially; incrementing cost by 1 is completely different from adding 1 PBKDF2 iteration. Bcrypt also has implementation-specific password length limits/behaviors, requiring care with encoding and long inputs.

Never design a generic `rounds=3` setting shared across all KDFs expecting it to mean the same thing. When migrating algorithms, **update the schema/parameters and algorithm ID accordingly**.

## 4. Output length: byte size of the result, not password strength

**Derived key length** specifies the physical size of the KDF output. With `PBKDF2WithHmacSHA256`, you can request a configurable bit length such as 128, 256, or 512 bits when appropriate for usage and supported by the provider.

| Output | Binary | Hex representation | Standard Base64 with padding |
| --- | ---: | ---: | ---: |
| 128 bits | 16 bytes | 32 ASCII chars | 24 chars |
| 256 bits | 32 bytes | 64 ASCII chars | 44 chars |
| 512 bits | 64 bytes | 128 ASCII chars | 88 chars |

**Warning:** a 256-bit output **does not mean 256-bit password security**. If the password is drawn from a small guessable set, an attacker can run the KDF on candidate passwords. Increasing output length does not increase the password's search space.

### 4.1. Output sizes by purpose

- **Password verifier:** pick output length per algorithm/policy design. Store enough bytes for comparison; avoid arbitrary truncation without specification.
- **AES-128 key:** requires a 16-byte key; **AES-256** requires a 32-byte key. Only use KDF output directly as a key when KDF, salt, context, and key lifecycle are properly designed.
- **HMAC key:** key material length and MAC output length are distinct quantities; a 32-byte KDF output does not automatically dictate a 32-byte MAC in every algorithm.
- **HKDF after password KDF:** a design may derive a suitable intermediate secret and then derive purpose-specific keys via HKDF; clearly define domain, context, and root/intermediate key protection. Never reuse one raw output directly across multiple functions.

In RFC PBKDF2, `dkLen` is in **bytes**, bounded by PRF blocks. In Java `PBEKeySpec`, `keyLength` is in **bits**. Check both parameter name **and unit** before passing values to an API.

### 4.2. Bytes, bits, hex, and Base64 are not the same number

A 32-byte verifier may be stored in a DB as **64 hex characters** or **44 padded standard Base64 characters**. With unpadded Base64URL, 32 bytes become **43 ASCII characters**. This is encoding overhead; **it does not change the KDF algorithm**.

Example:

```java
byte[] derived = /* KDF output, e.g., 32 bytes */;
String encoded = java.util.Base64.getUrlEncoder()
        .withoutPadding().encodeToString(derived);
```

This snippet is not a standalone program. **Never convert arbitrary digest bytes directly with `new String(derived, UTF_8)`**, because a digest can contain byte sequences that are invalid in UTF-8.

### 4.3. Salt length and output length are independent

A configuration with a **16-byte salt + 32-byte output** is completely normal. There is no rule that salt length must equal hash length, or that output length must match password string length. For the sample record:

- Salt: 16 random bytes = 128 bits, typically 22 characters in unpadded Base64URL.
- Derived verifier: 32 bytes = 256 bits, 43 characters in unpadded Base64URL.
- Iterations: a cost integer, **not bits/bytes**.
- Version: a policy identifier, **not a security level**.

## 5. Configuration version: verifying legacy data and upgrading new data

KDF parameters must evolve over time as hardware speeds up, new algorithms gain support, policies change, or new security requirements emerge. If you store only the hash **without storing salt/algorithm/cost/size**, the system may not know how to recompute verification for older accounts.

A **configuration version** is a policy label that helps manage history. It **does not replace** storing the critical parameters of each record.

Distinction example:

| Field | Role |
| --- | --- |
| `formatVersion` | Schema/record or application policy version, e.g., v1/v2 |
| `algorithm` | Exact algorithm/KDF used when creating the record |
| `iterations` or `timeCost/memoryCost/parallelism` | Actual cost parameters of the record |
| `derivedKeyBits` | Output length used |
| `salt` | Actual salt bytes of the record |
| `hash/verifier` | Stored result bytes for comparison |
| `encoding` | How bytes are represented as text, e.g., Base64URL |
| `pepperKeyId` (if used) | External key identifier outside DB, not the secret pepper value |

### 5.1. Distinguishing three types of “version”

1. **Application policy version:** defined by operations, e.g., `policy=2` when raising cost or switching KDFs. Policy names are internal metadata and must be interpreted against a concrete schema.
2. **Record format version:** version of how records are serialized/deserialized; can change without changing the KDF (e.g., migrating from two DB columns to a standard encoded string).
3. **Algorithm version:** the version of *the algorithm itself* in certain families (e.g., Argon2 has a version parameter). This differs from an application-assigned version.

Do not use a `v=2` field to vaguely mean “guaranteed strong.” A record labeled v2 whose iterations were altered down to 1 is still dangerous if code fails to validate policy and parameter bounds.

### 5.2. Self-describing record template

A representation can use a structure such as:

```text
formatVersion | algorithm | iterations | outputBits | saltBase64Url | verifierBase64Url
```

Or standard structures provided by password-hashing libraries, such as the **PHC string format** where appropriate. What matters is that the server understands and validates every field. Never invent a delimiter-separated string that could collide with unescaped data; production requires strict parsing, length limits, and handling of unsupported versions.

**Never store the pepper inside the record**, if one is used. The pepper belongs inside the secret manager/KMS boundary and is selected by an appropriate key ID/version.

### 5.3. Login flow with legacy records and upgrades

Suppose the server reads a v1 record while the current policy is v2:

1. **Read the old record** and validate format/algorithm/parameter bounds against an allowlist. Never accept excessive iteration counts or unsupported configurations that trigger resource exhaustion during verification.
2. **Verify the entered password** using **the v1 record's own salt and parameters**, rather than substituting v2 policy before recomputing; doing so would break all existing passwords.
3. If it does not match, **reject login** and do not upgrade the record.
4. If it matches, generate a **fresh salt**, run the **current v2 policy KDF** with the **entered password still in hand**, and create a new verifier.
5. **Persist the new record** atomically via a transaction or compare-and-swap on the old record's version/etag to avoid overwriting concurrent upgrades or password changes.
6. Clear temporary password data as far as feasible, verify policy compliance, and retain appropriate audit metadata.

This is **rehash on successful login**. You cannot “raise iterations” by simply re-hashing the old verifier and pretending it equals running the KDF on the original password; without the original password, you cannot evaluate the new KDF expression. For accounts that rarely log in, you may need to retain legacy verification for a defined window or require a password reset per policy.

### 5.4. Changing algorithms or raising costs must not break login

Migration control practices:

- **All new registrations/password changes:** create records under the current policy.
- **Successful login on an old account:** verify with old parameters, rehash under current policy, update atomically.
- **Failed login:** keep the old record, return a generic error, and enforce rate limiting.
- **Record using a retired algorithm or violating minimum policy:** route through an approved migration/reset branch rather than silently permitting weak algorithms forever.
- **Unparseable record:** fail closed; do not exhaustively try arbitrary algorithms/configurations.
- **Password change:** hash the new password with a fresh salt and current parameters, marking the new version.
- **Application rollback:** only perform if the rollback version understands newer records or a compatibility plan exists; never silently downgrade records to weaker configurations.

## 6. Java 17+: creating, verifying, and rehashing verifiers by version

The standalone example below uses **PBKDF2WithHmacSHA256** built into JCA/JCE to illustrate **all four parameters**. It generates a 16-byte salt with `SecureRandom`, derives a 256-bit output, stores configuration with the record, verifies using stored parameters, and upgrades a v1 record to v2 **after the correct password is confirmed**.

The values **100,000 and 180,000 iterations are solely for running the demo quickly and illustrating version differences; they are not deployment configuration targets**. In production, select the password KDF and cost from current guidance and your own benchmarks.

Save as **PasswordPolicyDemo.java**:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class PasswordPolicyDemo {
    static final String ALG = "PBKDF2WithHmacSHA256";
    static final int HASH_BITS = 256;
    static final int OLD_ROUNDS = 100_000;
    static final int CURRENT_ROUNDS = 180_000;
    static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();
    static final Base64.Decoder DECODER = Base64.getUrlDecoder();

    record Credential(int version, String algorithm, int iterations,
                      int bits, String saltBase64Url, String hashBase64Url) {}

    static byte[] pbkdf2(char[] password, byte[] salt,
                         int iterations, int bits)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, bits);
        try {
            return SecretKeyFactory.getInstance(ALG)
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static Credential enroll(char[] password, int version, int iterations)
            throws GeneralSecurityException {
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        byte[] hash = pbkdf2(password, salt, iterations, HASH_BITS);
        try {
            return new Credential(version, ALG, iterations, HASH_BITS,
                    ENCODER.encodeToString(salt),
                    ENCODER.encodeToString(hash));
        } finally {
            Arrays.fill(hash, (byte) 0);
        }
    }

    static boolean verify(char[] password, Credential stored)
            throws GeneralSecurityException {
        // Record-reading policy: reject unsupported algorithms/parameters.
        if (!ALG.equals(stored.algorithm()) || stored.version() < 1
                || stored.version() > 2 || stored.iterations() < 10_000
                || stored.iterations() > 1_000_000
                || stored.bits() != HASH_BITS) {
            return false;
        }

        byte[] salt;
        byte[] expected;
        try {
            salt = DECODER.decode(stored.saltBase64Url());
            expected = DECODER.decode(stored.hashBase64Url());
        } catch (IllegalArgumentException invalidEncoding) {
            return false;
        }
        if (salt.length != 16 || expected.length != HASH_BITS / 8) {
            return false;
        }

        byte[] actual = pbkdf2(password, salt,
                               stored.iterations(), stored.bits());
        try {
            return MessageDigest.isEqual(expected, actual);
        } finally {
            Arrays.fill(actual, (byte) 0);
        }
    }

    static boolean needsUpgrade(Credential c) {
        return c.version() < 2 || c.iterations() < CURRENT_ROUNDS;
    }

    public static void main(String[] args) throws Exception {
        char[] password = "example-password-only".toCharArray();
        Credential old = enroll(password, 1, OLD_ROUNDS);
        Credential another = enroll(password, 1, OLD_ROUNDS);

        System.out.println("salt bytes: "
                + DECODER.decode(old.saltBase64Url()).length);
        System.out.println("derived bytes: "
                + DECODER.decode(old.hashBase64Url()).length);
        System.out.println("correct password: " + verify(password, old));
        System.out.println("wrong password: "
                + verify("wrong-password".toCharArray(), old));
        System.out.println("distinct salts: "
                + !old.saltBase64Url().equals(another.saltBase64Url()));
        System.out.println("distinct hashes: "
                + !old.hashBase64Url().equals(another.hashBase64Url()));

        Credential changedSalt = new Credential(
                old.version(), old.algorithm(), old.iterations(), old.bits(),
                another.saltBase64Url(), old.hashBase64Url());
        System.out.println("changed salt rejected: "
                + !verify(password, changedSalt));
        System.out.println("old needs upgrade: " + needsUpgrade(old));

        if (verify(password, old)) {
            Credential fresh = enroll(password, 2, CURRENT_ROUNDS);
            System.out.println("new verifies: " + verify(password, fresh));
            System.out.println("new needs upgrade: " + needsUpgrade(fresh));
        }
        Arrays.fill(password, (char) 0);
    }
}
```

Compile/run with Java 17+:

```bash
javac -encoding UTF-8 PasswordPolicyDemo.java
java PasswordPolicyDemo
```

Expected stdout (KDF behavior verified with Java; random salt bytes are not printed):

```text
salt bytes: 16
derived bytes: 32
correct password: true
wrong password: false
distinct salts: true
distinct hashes: true
changed salt rejected: true
old needs upgrade: true
new verifies: true
new needs upgrade: false
```

**Reading the code parameter by parameter:**

- **Salt:** `new SecureRandom().nextBytes(salt)` generates a distinct 16-byte salt when `enroll()` runs. Two enrollments of the same password yield different salts and different verifiers. Both salt and verifier are Base64URL-encoded (unpadded) to illustrate text storage.
- **Iterations:** `PBEKeySpec(..., iterations, bits)` passes each record's round count. `verify()` reuses `stored.iterations()`; the v2 rehash uses `CURRENT_ROUNDS`. The check bounds in `verify()` are demo guards against executing unchecked configurations.
- **Output length:** `HASH_BITS = 256` corresponds to a 32-byte output; `HASH_BITS / 8` validates the decoded hash array length.
- **Version:** `Credential` stores `version` and `algorithm` along with parameters. `needsUpgrade()` compares against the new policy; the new record is created only inside the branch where the password has been verified.
- **Holding the password:** `char[]` and `PBEKeySpec.clearPassword()` cut down some unnecessary retention, though they do not guarantee the entire password vanishes immediately from JVM memory; the demo input is a string literal—never hardcode real passwords like that.
- **Comparison:** `MessageDigest.isEqual(byte[], byte[])` is used on the verifier byte arrays. Avoid converting binary outputs to strings without explicit encoding; never log verifiers or passwords.
- **Anti-resource-exhaustion rules:** `verify()` bounds version, iterations, output size, and salt length. When handling records from a potentially tampered DB, apply an **allowlist + practical policy bounds** before invoking the KDF to prevent DoS via huge iteration counts.
- **Persistence:** the example only creates `record` instances in memory; database **transaction/CAS** updates are not simulated as implemented. Real applications require atomic updates and protection against concurrent password changes/rehashes.

The “distinct salts/hashes” statements hold with overwhelming probability when the RNG works properly; two independent 128-bit random salts colliding is extraordinarily rare, though not mathematically impossible.

### 6.1. How does the demo configuration differ from production?

The program intentionally simplifies things to clarify data flow:

- The demo has only **two versions** of the same PBKDF2 algorithm; production may need a **registry** for multiple algorithms, pepper key IDs, and multiple coexisting versions.
- The demo encodes records as Java fields and omits a DB parser or serialized format with tamper resistance on metadata; in real deployments, schema validation and DB write controls matter greatly.
- The demo checks passwords in memory without login endpoint defenses (rate limiting, MFA, safe logging, abuse detection).
- The demo displays iteration counts for explanation, not benchmarking, and makes no guarantee about runtime on another JVM.
- The demo does not hand off KDF output as an encryption key; using a KDF for encryption requires designing key lifecycle and data protection accordingly.

## 7. Implementing versioning and upgrades without losing data

### 7.1. Each record self-describes the configuration that created it

A credential stored with PBKDF2 at 100,000 rounds and a 16-byte salt must **be verified using those exact parameters**; even if the application raised policy to 180,000 rounds, you cannot arbitrarily ignore old metadata.

Avoid designs that rely only on current global variables:

```text
CURRENT_ROUNDS = 180000
verify(oldCredential, password) = PBKDF2(password, oldSalt, CURRENT_ROUNDS)
```

That pattern will **produce the wrong result** for v1 records. Instead, select the stored algorithm and cost from the record after the parser validates them, verify first, and then rehash under the current policy.

### 7.2. Upgrading at successful authentication

A clear deployment workflow:

```text
READ credential record
    -> VALIDATE supported schema, alg, cost and length limits
    -> VERIFY using stored parameters
       -> mismatch: reject, do not modify credential
       -> match:
          -> if current policy satisfied: sign in
          -> else: generate NEW salt + current parameters
                   derive NEW verifier from entered password
                   persist atomically (version/CAS condition)
                   sign in
```

When the new current policy uses **Argon2id** while the legacy record uses **PBKDF2**, the old verifier is still verified via PBKDF2; after success, you can migrate to Argon2id via an approved library. Never pick a new algorithm implicitly from `hash.length` or ad-hoc strings.

### 7.3. Parameter tuning must consider performance and abuse

Operational risks:

- A large wave of concurrent account upgrades can spike CPU/memory usage; plan capacity accordingly.
- If an attacker can make the server process a record with huge `iterations` or excessive `memoryCost`, the login endpoint becomes vulnerable to DoS. Validate bounds before calling the KDF.
- Raising cost without limiting retries still lets attackers impose heavy load on the verification service.
- Allowing easy “downgrades” via client headers or user-modifiable records can leave flows stuck on weak policies indefinitely.
- Changing Unicode normalization/encoding rules for passwords without versioning can make the same displayed string yield different input bytes, locking out legitimate users.

## 8. Password encoding, Unicode, and interoperability

Salts and verifiers are byte arrays. Yet users enter **characters**; when passing a password to a KDF, character-to-byte conversion must be explicit per algorithm/provider.

- With `PBEKeySpec`, the input is a Java `char[]` (UTF-16 code units); the KDF provider handles encoding per algorithm/provider definition. When **interoperability between Java and another language** is needed, verify exact encoding rules with test vectors and record them in the version; never assume all libraries apply the same Unicode transformation.
- Some systems apply Unicode normalization (e.g., NFC) before the KDF; others do not. This is a compatibility and security decision that must remain stable for existing records. **Do not add a normalization step in a new version without a migration plan.**
- Never use `String.length()` to measure a password's UTF-8 byte length; encode properly before counting bytes. For bcrypt, mind implementation-specific input byte limits, especially with Unicode.
- Keep test vectors containing Vietnamese diacritics, non-BMP characters, known salts, and known parameters to verify compatibility across clients, servers, and new server versions.

Protect password inputs in transit with TLS, and keep passwords out of URLs, logs, analytics, exceptions, and crash reports. At the application level, do not arbitrarily trim or change password casing: doing so can break correctness and shrink the password space.

## 9. Salt, iteration count, and version in encryption key derivation

When a password KDF produces an **AES key to unlock data**, the parameters play similar roles, but upgrade consequences differ from password verifiers:

- Changing salt, iterations, KDF, or output length **produces different key bytes**, so previously encrypted data may no longer decrypt.
- Store KDF metadata alongside the encrypted data envelope, or maintain a key-version and salt system mapped to each payload.
- To upgrade configuration, you typically need the password, re-derive the old key, **decrypt safely**, and re-encrypt under the new key; or use a **key-encryption key / data-encryption key** design that supports rewrapping.
- If using the same password for both verifier and encryption, never use **the exact same derived bytes** directly for both purposes. Separate KDF purposes/contexts clearly or add an HKDF step to derive scoped subkeys from appropriate intermediate material.
- Choosing a 32-byte output for AES-256 **does not prove 256-bit key entropy** if the password is weak. Security also depends on whether an attacker has an offline oracle to test passwords.
- Manage the cipher's **nonce/IV** separately from the KDF salt. For AES-GCM, for example, the nonce must be unique per AES key; it cannot be replaced with “some random salt” while ignoring nonce uniqueness rules.

For password verifiers, rehash on successful login is simpler because the server only stores a new verifier. For encryption, you must ensure **old data remains recoverable** before replacing keys or wrapping keys.

## 10. Common mistakes and consequences

| Mistake | Consequence | Fix |
| --- | --- | --- |
| One salt for all accounts | Same password produces same verifier, easing multi-target attacks | Generate an independent random salt per record |
| Treating salt as a secret key | Misaligned security boundary and inadequate password protection | Salts are public; if using a pepper, manage that secret separately |
| Deriving salt from email, username, or timestamp | Predictable, repeatable, or insufficient entropy | Use a CSPRNG with length per KDF/policy |
| Increasing output 256 → 512 bits to “boost password entropy” | Does not make weak passwords harder to guess | Require strong passwords/passphrases and proper KDF cost |
| Using fast SHA-256 directly | Cheap offline guessing of many candidates | Choose a properly costed password KDF |
| Passing `32` to `PBEKeySpec` when wanting 32 bytes | Requests 32-bit output by mistake | Pass **256 bits**, validate byte length |
| Raising PBKDF2 iterations by guesswork alone | May be too weak or cause slowness/DoS | Benchmark, enforce policy, limit concurrency and rate limit |
| Applying the same iteration count to Argon2id/bcrypt | Completely different algorithmic cost models | Use each KDF's proper parameter set |
| Storing only the digest without salt/cost/alg | Cannot verify or migrate old records | Store a self-describing format and policy version |
| Verifying old records with current policy parameters | Users with valid passwords get rejected | Verify with stored config, rehash after passing |
| Editing iteration count in DB while keeping old verifier | Verifier no longer matches the password | Rehash using the **correct password** and a fresh salt |
| Letting records declare unbounded cost | DoS via excessively heavy KDF work | Allowlist and bound parameters before execution |
| Arbitrarily truncating/encoding digests | Verifier mismatch or weakened comparison below policy | Store exact output bytes and explicit encoding |
| Ignoring Unicode normalization/versioning | Valid passwords can stop working | Keep encoding rules consistent per version with test vectors |
| Using one KDF output as verifier/AES/HMAC key | Cross-purpose key reuse | Separate key material/contexts/purposes cleanly |
| Writing plaintext passwords or pepper to DB/logs | Credential/secret exposure | Store only verifier, salt, and metadata; isolate pepper |
| Printing full verifiers for debugging | Increases exposure of material enabling offline attacks | Log non-sensitive metadata and correlation IDs; restrict DB access |

## 11. Checklist for auditing a password KDF configuration

1. **Algorithm:** is the selected KDF appropriate for password hashing vs. password-based key derivation and your operating constraints?
2. **Salt:** is there an **independent random salt** per record, long enough and stored with exact bytes, without confusion with pepper/nonce?
3. **Cost:** are PBKDF2 iterations or Argon2id memory/time/parallelism benchmarked on deployment hardware and aligned with current policy?
4. **Output:** are API bit vs. byte units clear; do verifiers have the expected byte length and encoding?
5. **Version:** does the record store alg, params, salt, output, and format/policy version; does the parser enforce allowlists, bounds, and unsupported-version handling?
6. **Verification:** does it use the old record's exact parameters, constant-time byte comparison, rate limiting, and leak-free errors/logs?
7. **Migration:** upon valid login, does it rehash under current policy with a fresh salt and atomic update? Is there a migration/reset plan for inactive accounts?
8. **Encoding:** is Unicode password handling consistent across JVM/providers, product versions, and clients?
9. **Secret/pepper:** if a pepper is used, is it managed outside the DB with a rotation/recovery process?
10. **Crypto usage:** if the output becomes an encryption key, are restore/rewrap/re-encrypt flows, key separation, and independent IV/nonce handling designed?

## 12. Scenario questions for self-testing

**Question 1.** Alice and Bob choose the same password; the system uses PBKDF2 with independently generated 16-byte salts. Must their two verifiers be identical?  
**Answer:** **No**. Different salts almost certainly produce different KDF outputs, even with identical passwords and parameters.

**Question 2.** A salt leaks, while the password has not leaked. Does the system immediately lose all security?  
**Answer:** Not solely from the salt leaking, because salts are not meant to be secret. However, if an attacker has both the verifier and salt, they can guess passwords offline; password strength and KDF cost remain critical.

**Question 3.** A new policy raises PBKDF2 iterations from an old count to a higher count. When checking login for an old record, which count do you use?  
**Answer:** Use the **iterations stored in the old record** to verify; once the password matches, rehash using the **new policy's** iteration count and a fresh salt.

**Question 4.** `PBEKeySpec` needs a 32-byte output. What should `keyLength` be?  
**Answer:** **256**, because Java expects the length in bits. The resulting `byte[].length` will be **32**.

**Question 5.** Does changing output from 32 bytes to 64 bytes make the password “password123” twice as strong?  
**Answer:** **No**. A longer output does not add entropy to a guessable password. Guessing cost and password quality must be evaluated separately.

**Question 6.** A user has a v1 verifier, but the database row was altered to `iterations=999999999`. Should the backend execute the KDF with that value?  
**Answer:** **No**. Validate version/algorithm and bound cost before executing; invalid data must be rejected and handled per policy.

**Question 7.** Given the same password, salt, and KDF parameters, two implementations use different Unicode encoding rules. Are the verifiers guaranteed to match?  
**Answer:** **No**. Document how passwords map to input bytes, maintain cross-platform test vectors, and version any changes.

**Question 8.** A record stores a 32-byte output, 16-byte salt, and algorithm name, without storing the iteration count. Is that enough to verify multiple versions deterministically?  
**Answer:** **Not enough** if different versions use different round counts. You must store the iteration count or maintain an unambiguous, long-lived version → parameters mapping.

**Question 9.** You change the user's password and salt, while keeping data encrypted with the key derived from the old password. Will the data automatically open with the new key?  
**Answer:** **No**. You must design decryption/re-encryption or key wrapping/rewrapping according to your key management and versioning architecture.

### Key takeaway

**Salt** guarantees distinctness across records; **iteration/cost** makes every password guess more resource-intensive; **output length** defines the byte size of the result; **configuration version** preserves verifiability, upgradability, and compatibility. Operating a password KDF safely requires all four, plus strong passwords, login attempt limits, consistent Unicode handling, and clear configuration lifecycle management.
