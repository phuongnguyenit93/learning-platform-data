# 7.4. PBKDF2 via `SecretKeyFactory` and `PBEKeySpec` in Java 21

**PBKDF2** (*Password-Based Key Derivation Function 2*) turns a user-chosen password into derived bytes by combining a **salt**, an **iteration count**, and a pseudorandom function (**PRF**, typically HMAC). In Java 21, you can use PBKDF2-HMAC-SHA256 through the standard JCA/JCE `SecretKeyFactory` and `PBEKeySpec` APIs, without extra dependencies for basic examples.

This topic belongs to **“7. Passwords and Key Derivation”** in the Java Advanced – Security & Cryptography module. The focus is on understanding the parameters properly, using Java APIs to derive/verify passwords, storing verifiable records for later checks, choosing appropriate costs, and recognizing the security limits of PBKDF2.

## Objectives

After completing this lesson, you will be able to:

1. Explain `PBKDF2(P, S, c, dkLen)` and the roles of **password**, **salt**, **iterations**, **PRF**, and **derived-key length**.
2. Distinguish **password hashing for login verification** from **key derivation for encryption**, and distinguish salt from pepper.
3. Use `new PBEKeySpec(char[], byte[], int, int)` and `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` to generate derived bytes.
4. Build a record containing version/algorithm/cost/salt/hash, and verify by re-deriving and comparing safely.
5. Verify Java 21 examples with accurate results, handle password memory carefully, avoid weak salts, and choose parameters on a sound basis.
6. Explain when PBKDF2 is an appropriate choice, when Argon2id should be considered, and how to upgrade parameters without locking out accounts.

## 1. The problem PBKDF2 solves

A password such as `"my-password"` usually has far less entropy than a random 256-bit key. **Never** store plaintext passwords, never store decryptable ciphertexts for login, and never store raw `SHA-256(password)` as a password verifier: SHA-256 computes so fast that an attacker with a copy of the database can test vast numbers of candidates.

PBKDF2 increases the cost of testing a single password by repeating a PRF many times. Given the same password and the **same** salt/iterations/PRF/key length, the output is **deterministic**; given a different salt, the output is almost certainly different.

```text
Password (P) --\
                +--> PBKDF2(PRF, iterations=c) --> Derived key (DK)
Random salt (S)-/                         |
                                         \--> store/verifier or use as key material
```

**PBKDF2 does not “encrypt passwords.”** It is a key derivation function; when applied to login verification, the application stores the **derived value** and parameters, not the password. The user logging in submits a candidate password; the server recomputes PBKDF2 using the stored salt/cost and compares.

**Passwords can still be guessed offline** if the hash database leaks; PBKDF2 makes guessing more CPU-expensive, but does not replace strong passwords, MFA, access controls, intrusion monitoring, login attempt limits, or secret-leak prevention.

## 2. Five inputs and the output

Standard notation:

```text
DK = PBKDF2(P, S, c, dkLen; PRF)
```

| Component | Meaning | Example in this lesson |
| --- | --- | --- |
| `P` | Password, the secret known by the user. In Java, the API accepts `char[]`; character-to-byte conversion rules must align across systems. | `char[] password` |
| `S` | Salt: random bytes **unique per record**, does not need to be secret. | `byte[16]` = 128 bits from `SecureRandom` |
| `c` | PBKDF2 iteration count, a **positive integer**; raising `c` makes every guess take longer. | `600_000` rounds in the password-storage example |
| `dkLen` | Output length, **measured in bytes in the PBKDF2 formula**. | 32 bytes |
| `PRF` | Pseudorandom function, typically `HMAC-SHA256` or `HMAC-SHA512`. | `HMAC-SHA256` |
| `DK` | Derived bytes of the chosen length. | `byte[32]` |

**A very easy mistake:** the `keyLength` parameter in Java's `PBEKeySpec(password, salt, iterationCount, keyLength)` constructor is in **bits**, not bytes. To get a 32-byte output, pass **256**, not 32.

A 16-byte salt freshly chosen for **every hash creation / every account** is a common choice. Salts can be stored publicly alongside the hash; there is no need to “encrypt the salt” for extra security. Salts defeat precomputed tables and ensure two users with the same password do not share the same hash record. A salt is **not a secret key** and does not by itself block guessing weak passwords.

**Pepper** differs from salt: a pepper is an application-level secret usually stored separately from the database (KMS/HSM or secret manager). A pepper can add defense in depth, but requires a rotation, key-loss, and recovery plan; pepper cannot replace salt or work factor.

## 3. How does PBKDF2 work?

With `PBKDF2WithHmacSHA256`, the PRF is HMAC-SHA256 with a 32-byte output. PBKDF2 computes output blocks via repeated PRF chains and XOR operations.

For the `i`-th block (1-indexed), as specified in RFC 8018:

```text
U_1 = PRF(P, S || INT_32_BE(i))
U_2 = PRF(P, U_1)
U_3 = PRF(P, U_2)
...
U_c = PRF(P, U_(c-1))

T_i = U_1 XOR U_2 XOR ... XOR U_c
DK  = (T_1 || T_2 || ... ) truncated to dkLen bytes
```

Here `INT_32_BE(i)` is the block index encoded as a 4-byte big-endian integer; `||` denotes concatenation. Requesting 32 bytes from HMAC-SHA256 requires only one block; requesting 64 bytes requires two blocks. Computation time scales roughly linearly with iteration count and number of output blocks.

Several important properties:

- Identical `P, S, c, dkLen, PRF` must yield identical `DK` when password-to-byte conversion is identical.
- Raising `c` does not give the password more entropy; the goal is to make **each attempt** take more time.
- A fresh salt does not make a password stronger, but prevents reusing precomputed lookup results across all accounts.
- Generating a 256-bit `DK` does not turn a password with a few bits of entropy into a random key with 256 bits of entropy.
- PBKDF2 is primarily CPU-bound and **not memory-hard** like Argon2id; therefore it is not the default top preference for every new password system.

Normally, **never implement** the `U_i`/XOR loop yourself in a Java application. Use the tested JCA/JCE implementation and focus on salt, cost, storage, comparison, and lifecycle management.

## 4. Java 21 API: `SecretKeyFactory` + `PBEKeySpec`

Primary imports:

```java
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.security.SecureRandom;
```

Basic API flow:

```java
char[] password = /* password obtained from secure input */;
byte[] salt = new byte[16];
new SecureRandom().nextBytes(salt);

PBEKeySpec spec = new PBEKeySpec(password, salt, 600_000, 256);
try {
    SecretKeyFactory factory =
            SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
    byte[] derived = factory.generateSecret(spec).getEncoded();
    // Use derived for its intended purpose; do not log and clear when done.
} finally {
    spec.clearPassword();
    // The caller remains responsible for handling/clearing its own password array.
}
```

**This is an illustrative snippet**, not a standalone runnable Java file: the `password` variable must come from real input and the `derived` bytes must be managed within an appropriate scope. Sections 5 and 6 provide complete, compilable programs.

Components:

- `PBEKeySpec` describes **password, salt, iteration count, and key length**. Its constructor checks that salt is non-null/non-empty and count/key length are positive; it **clones** the password and salt internally.
- `clearPassword()` clears **the copy inside `PBEKeySpec`**, not the original array held by the caller. When no longer needed, the caller must call `Arrays.fill(password, '\0')` in a `finally` block. `getPassword()` returns a copy; avoid calling it just to inspect or log.
- `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` selects an implementation from a **security provider** supporting this algorithm name. This name is in Java Security Standard Algorithm Names; SunJCE in JDK 21 supplies an implementation. Not every third-party provider is required to support it.
- `generateSecret(spec)` produces a `SecretKey`. With providers that support exporting key material, `getEncoded()` returns the derived key bytes (as in the PBKDF2 demo). A provider may refuse export and return `null`; production code should handle that case.
- `getEncoded()` contains sensitive bytes: do not convert it to a `String` for logging, do not return it in an API response, and keep it in RAM only as long as necessary.
- `NoSuchAlgorithmException` indicates the provider/runtime lacks the algorithm; `InvalidKeySpecException` or parameter errors on password/salt/cost should be handled as configuration/implementation errors rather than equated with “user entered the wrong password.”

**Unicode and compatibility note:** `PBEKeySpec` Javadoc notes that password-based mechanisms may use varying numbers of bits per character; provider docs also list specific limits. When matching hashes across Java, Node.js, Python, or different providers, explicitly define encoding/normalization and test with passwords containing **diacritics, emojis, and combining characters**; never assume two runtimes passed `"mật khẩu"` yield identical input bytes. The deterministic test-vector example below uses ASCII to avoid Unicode assumptions.

## 5. Verification experiment: PBKDF2-HMAC-SHA256 test vectors

The first example uses ASCII password `password`, ASCII salt `salt`, 256-bit output, and only **1 or 2 iterations** to produce byte-verifiable test vectors. This low cost is strictly for **functional testing**; never use 1–2 iterations to store user passwords.

Create **`Pbkdf2Vector.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class Pbkdf2Vector {
    public static void main(String[] args) throws Exception {
        char[] password = "password".toCharArray();
        byte[] salt = "salt".getBytes(StandardCharsets.US_ASCII);
        try {
            for (int iterations : new int[] {1, 2}) {
                PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, 256);
                try {
                    byte[] derived = SecretKeyFactory
                            .getInstance("PBKDF2WithHmacSHA256")
                            .generateSecret(spec).getEncoded();
                    System.out.println(iterations + ": " +
                            HexFormat.of().formatHex(derived));
                    Arrays.fill(derived, (byte) 0);
                } finally {
                    spec.clearPassword();
                }
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

In a terminal using JDK 21 (or a newer compiler supporting `--release 21`):

```text
javac -version
javac --release 21 -encoding UTF-8 Pbkdf2Vector.java
java Pbkdf2Vector
```

Exact stdout:

```text
1: 120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b
2: ae4d0c95af6b46d32d0adff928f06dd02a303f8ef3c251dfd6e2d85a95474c43
```

You should be able to explain:

- Only **`iterations`** differs between inputs, so the outputs differ.
- Each hexadecimal result is 64 characters = 32 bytes = 256 bits.
- `HexFormat` is used to **display test results**; it does nothing to make PBKDF2 stronger.
- This code is strictly a functional vector; for real passwords, salts must be long/random per record and iteration counts must be sufficiently high.

## 6. Complete password storage and verification example

Goal: a registration API generates a random salt and storage record; at login, the server reads the record and re-runs PBKDF2 on the candidate password. No password decryption exists.

Record format used in the example:

```text
pbkdf2-sha256:600000:<salt-base64url>:<hash-base64url>
```

Here `pbkdf2-sha256` identifies the algorithm, `600000` is the work factor used at creation, `salt` is 16 random bytes Base64URL-encoded, and `hash` is 32 derived bytes Base64URL-encoded. The `:` character is solely a delimiter **defined by this sample application**, not a universal format across all Java libraries. Base64 encodes bytes into text fields; it is **not secret encryption**.

Create **`PasswordHashDemo.java`**:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordHashDemo {
    private static final String ALGORITHM = "PBKDF2WithHmacSHA256";
    private static final String ID = "pbkdf2-sha256";
    private static final int SALT_BYTES = 16;
    private static final int KEY_BITS = 256;
    private static final int ROUNDS = 600_000;
    private static final int MAX_ROUNDS = 3_000_000;
    private static final SecureRandom RANDOM = new SecureRandom();

    static byte[] derive(char[] password, byte[] salt,
                         int iterations, int bits)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, bits);
        try {
            byte[] derived = SecretKeyFactory.getInstance(ALGORITHM)
                    .generateSecret(spec).getEncoded();
            if (derived == null || derived.length != bits / 8) {
                throw new GeneralSecurityException("PBKDF2 output unavailable");
            }
            return derived;
        } finally {
            spec.clearPassword();
        }
    }

    static String createRecord(char[] password)
            throws GeneralSecurityException {
        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);
        byte[] derived = derive(password, salt, ROUNDS, KEY_BITS);
        try {
            Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();
            return ID + ":" + ROUNDS + ":" +
                    encoder.encodeToString(salt) + ":" +
                    encoder.encodeToString(derived);
        } finally {
            Arrays.fill(derived, (byte) 0);
        }
    }

    static boolean verify(char[] candidate, String record)
            throws GeneralSecurityException {
        String[] fields = record.split(":", -1);
        if (fields.length != 4 || !ID.equals(fields[0])) {
            return false;
        }
        int iterations;
        byte[] salt;
        byte[] expected;
        try {
            iterations = Integer.parseInt(fields[1]);
            if (iterations < ROUNDS || iterations > MAX_ROUNDS) {
                return false;
            }
            Base64.Decoder decoder = Base64.getUrlDecoder();
            salt = decoder.decode(fields[2]);
            expected = decoder.decode(fields[3]);
        } catch (IllegalArgumentException e) {
            return false;
        }
        if (salt.length != SALT_BYTES || expected.length != KEY_BITS / 8) {
            Arrays.fill(expected, (byte) 0);
            return false;
        }
        try {
            byte[] actual = derive(candidate, salt, iterations, KEY_BITS);
            try {
                return MessageDigest.isEqual(actual, expected);
            } finally {
                Arrays.fill(actual, (byte) 0);
            }
        } finally {
            Arrays.fill(expected, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        // String literals are for demo only; real passwords come from secure input.
        char[] registration = "correct horse battery staple".toCharArray();
        char[] correct = "correct horse battery staple".toCharArray();
        char[] wrong = "wrong password".toCharArray();
        try {
            String record = createRecord(registration);
            System.out.println("format: " + record.startsWith(ID + ":"));
            System.out.println("correct: " + verify(correct, record));
            System.out.println("wrong: " + verify(wrong, record));
        } finally {
            Arrays.fill(registration, '\0');
            Arrays.fill(correct, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
```

Compile and run:

```text
javac --release 21 -encoding UTF-8 PasswordHashDemo.java
java PasswordHashDemo
```

Exact stdout:

```text
format: true
correct: true
wrong: false
```

The program **does not print the record**; because the salt is random, the record string differs on every run. The derivations inside `verify` reuse **the exact stored salt and cost**, so the right password is accepted. The wrong password produces different bytes and returns `false`.

### 6.1 Line-by-line analysis of protections and limitations

**`RANDOM.nextBytes(salt)`** creates a fresh 16-byte salt; never use `Random`, timestamps, user IDs, or passwords as a source of “randomness.” To create a salt for a second user, call `createRecord` again to obtain a fresh salt.

**`ROUNDS = 600_000`** is the minimum currently cited in the OWASP Password Storage guidance for **PBKDF2-HMAC-SHA256** (at the time of writing). It is not a “forever safe” constant or guaranteed sufficient under all conditions. In practice, benchmark p95/p99 under heavy load, update as recommendations change, and respect server capacity. `MAX_ROUNDS = 3_000_000` is solely an **example** parsing/CPU guard ceiling; production systems define governed minimum/maximum policies considering migration and DoS protection.

**`PBEKeySpec` and `clearPassword()`:** `PBEKeySpec` holds a cloned copy of `char[]`, so call `clearPassword()` in `finally` even if `generateSecret` fails. The `char[]` passed into the API still belongs to the caller and must be cleared separately.

**`MessageDigest.isEqual(actual, expected)`** provides byte-array comparison suited for verifying tags/digests, avoiding hand-written loops that break on the first mismatched byte. The example validates that the hash length is 32 bytes before comparing. Do not infer that the entire endpoint runs in constant time: parsing time, iteration count, account existence, and error paths still vary.

**`Arrays.fill(derived, (byte) 0)`** wipes derived arrays held by application code. Java/JVM may keep copies in the provider, garbage collector, or external buffers; never claim “every copy of the secret has been erased from RAM.” Avoid creating unnecessary `String` objects holding passwords. The demo still uses string literals for test readability—**never apply literals like that to production passwords**.

**`verify` checks format and iteration/length bounds** before running PBKDF2 to avoid accepting malformed structures or abnormal costs. Even for records from a trusted database, bound string size before splitting/decoding; if records could be tampered with, treat them as untrusted input and separate data-format errors from wrong-password failures. Infrastructure/provider errors should be routed through internal error handling without returning crypto details to clients.

**Remaining limitations:** the demo does not cover password policies, rate limiting, MFA, sessions/tokens, user ID lookup, account lockout, safe logging, Unicode policy, pepper/KMS, cost benchmarking, or upgrading legacy hashes. Use it strictly as an API + record-format model, not as a complete authentication system.

## 7. What should be stored in the database?

A verifier record should contain enough information for future verification:

| Field | Example | Explanation |
| --- | --- | --- |
| `scheme/version` | `pbkdf2-sha256` | Identifies derivation/encoding method and format version. |
| `iterations` | `600000` | Must be stored per record, since work-factor policy changes over time. |
| `salt` | 16-byte Base64URL | Unique random salt per record; safe to store non-secret. |
| `derivedKey` | 32-byte Base64URL | Value used to verify passwords; protect as a password verifier. |
| `createdAt/rehashPolicy` (system-dependent) | Creation timestamp, config version | Aids administration and upgrades; not a required PBKDF2 input. |

**Do not store** plaintext passwords, “passwords encrypted for decryption,” or secret peppers in the same table. Avoid logging full hash records: even though not the original password, a record contains all public inputs needed for offline guessing if leaked. Protect backups, snapshots, DB access permissions, configuration secrets, and login flows.

At login time:

1. Look up the record by the defined identity/ID.
2. Validate scheme/format/bounds before computing.
3. Construct `PBEKeySpec` from the **candidate password** with the record's salt/iterations/keyLength.
4. Re-derive using the **exact PRF**, comparing bytes (avoid comparing hashes via `String` where avoidable).
5. If valid and the record's work factor is below the new policy, **rehash** with a fresh salt + new cost and persist safely (e.g., optimistic concurrency in a transaction) before or after creating a session per design.
6. Return a unified login error for wrong password / missing ID, enforce rate limiting, and monitor security events without leaking record details.

**Migrating from lower costs:** the demo's `verify` rejects counts below 600,000 because it intentionally enforces strict policy for new data. If a system has legacy 100,000-round records, production code needs a **controlled legacy verification path** that upgrades to 600,000 upon successful login; do not reuse the demo's `verify` directly for migration and accidentally lock out legacy accounts. When switching algorithms, dispatch by the version in the record and plan resets/migrations if an old algorithm is too weak.

## 8. Choosing iteration count and algorithm

PBKDF2 can be appropriate when a system requires a **built-in JDK implementation** or a specific compliance mode; for new password-storage systems, the [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) prefers **Argon2id** and treats PBKDF2-HMAC-SHA256 as an option requiring sufficiently high cost configuration (especially under FIPS constraints).

| Algorithm | Properties | Usage guidance |
| --- | --- | --- |
| `SHA-256(password)` or `MD5(password)` | Very fast, lacks proper work factor/salt | **Never** use for new password verifiers. |
| `PBKDF2WithHmacSHA1` | PBKDF2 with HMAC-SHA1; mainly legacy compatibility | Prefer `PBKDF2WithHmacSHA256` for new designs when PBKDF2 is needed. |
| `PBKDF2WithHmacSHA256` | CPU work factor + salt; available via Java 21/SunJCE `SecretKeyFactory` | Use when deployment requirements fit, benchmarked and aligned with current policy. |
| `scrypt` | Memory-cost KDF; not a standard general JDK `SecretKeyFactory` API | Consider when memory-hardness is needed with a vetted library. |
| `Argon2id` | Memory-hard, with memory/time/parallelism parameters | OWASP's preferred choice for new password systems; requires a trusted external library outside standard JDK. |

**How to benchmark properly:**

- Test on **production hardware/configuration** (CPU, worker count, container quotas, virtualized hardware), measuring PBKDF2 latency under low load and concurrent login bursts.
- Pick cost from the latest security guidance, latency budget, and credential-stuffing/DoS tolerance. Raising iterations consumes CPU for both **legitimate clients and attackers**; enforce rate limits, queues, and resource budgets.
- Enforce a **maximum** cap on iterations parsed from records/external inputs to prevent an attacker from forcing massive CPU usage on a single request.
- Store iterations per record, raise cost for new records, and upgrade records after successful user logins as needed.
- Always generate a fresh salt when rehashing and update the scheme version; never edit iterations on an old record while keeping the old hash, or valid passwords will stop matching.

**Cost is not standalone security:** attackers with GPUs/ASICs can still run many trials; weak passwords remain vulnerable. PBKDF2 does not replace strong password policies and account protections.

## 9. PBKDF2 for a password verifier vs. PBKDF2 for an AES key

`PBKDF2` returns *key material* and can serve multiple purposes; your design must specify **which purpose** from the start.

**A. Login password verification:** store `salt + iterations + derivedHash`. At login, compare outputs; there is never any decryption back to the password. A verifier record must never be reused directly as a user data encryption key.

**B. Deriving an encryption key from a passphrase:** the application needs salt, cost, and length matching the cipher (e.g., 32 bytes for AES-256), then builds a key from the derived bytes. Key derivation alone **is not enough**: use authenticated encryption such as AES-GCM with a distinct nonce/IV, never repeat an IV under the same key, store required metadata, and handle authentication failures, backups, and password changes. When sharing one passphrase across purposes, separate key domains via independent salts/contexts or an explicit KDF/key hierarchy; never use the exact same derived bytes as both a password verifier and an encryption key.

Non-standalone illustration (assuming `derived` is a properly derived `byte[32]`):

```java
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

// This only wraps key material as an AES key; no encryption is performed yet.
SecretKey aesKey = new SecretKeySpec(derived, "AES");
```

**Do not confuse PBKDF2 salt with AES-GCM IV/nonce.** Salt makes each password derivation independent; the cipher's IV/nonce ensures safe encryptions under the same key. Each has its own management rules. If encrypted data must later be decrypted using the same passphrase, you must store the salt/cost/IV/format used; changing the salt produces a different key unless you migrate/rewrap.

## 10. Common issues and troubleshooting

| Symptom or error | Common cause | How to check |
| --- | --- | --- |
| `NoSuchAlgorithmException: PBKDF2WithHmacSHA256` | JRE/provider does not provide the algorithm, or runtime differs from expected JDK | Check `java -version`, active providers, algorithm name, and JDK Providers Documentation for your version. |
| `InvalidKeySpecException` | Invalid spec or provider cannot convert it | Inspect `KeySpec` type, cost, length, and provider. |
| `IllegalArgumentException` in `PBEKeySpec` | Empty salt, non-positive iterations, or non-positive keyLength | Check constructor docs; pass non-empty salt, positive cost, and valid bit length. |
| `getEncoded() == null` | Provider refuses to export raw key bytes | Handle explicitly; never assume every `SecretKey` is extractable. |
| Password verification always fails | Mismatched salt/cost/PRF/encoding between creation and verify, or unversioned format change | Store all parameters, run test vectors, check Unicode/normalization. |
| Two accounts with the same password have the same hash | Shared salt, fixed salt, or salt not regenerated | Generate a fresh salt with `SecureRandom` for every record. |
| Poor login performance under heavy load | High cost, many concurrent requests, missing rate limit/resource budget | Benchmark on real hardware; limit concurrency and request rate. |
| Legacy records fail to log in after raising cost | Only changed configured iterations without rehashing, or verifier blocks legacy | Use record versioning and migrate after successful verification. |
| 1–2 round test vector passes, yet insecure | Vector checks **algorithm correctness**, not work factor | Use policy-compliant high cost, unique salts, and security testing. |
| Logs contain passwords/hashes/keys | Accidentally converting `char[]`/`byte[]` to `String` or debug printing | Remove secret logging, restrict debug access, and clear sensitive arrays after use. |

Additional note: `PBEKeySpec` takes `char[]`, whereas web APIs typically receive UTF-8 bytes that frameworks decode into `String`. You cannot completely erase immutable `String` objects that have passed through the JVM; clearing `char[]` is still worthwhile, but do not claim every trace of the secret has been purged. For cross-system compatibility, **define a normalization policy before creating records** and maintain it across all logins.

## 11. Practice exercises and checklist

1. **Parameters:** why does `new PBEKeySpec(password, salt, 600_000, 32)` not mean “32-byte hash”? Fix it to the right key length.
2. **Test vectors:** run `Pbkdf2Vector.java` and match both hexadecimal values exactly. Change `iterations=2` to `3` and explain why the output changes even though password and salt stay unchanged.
3. **Registration and login:** run `PasswordHashDemo.java`; add a second record creation from the same password and verify the two records' salts differ. Print only comparison booleans—avoid logging real records.
4. **Data model:** design a schema storing `scheme, cost, salt, hash` and a migration policy from 200,000 to 600,000 iterations without invalidating existing accounts.
5. **Calculations:** how many bits is a 16-byte salt? How many bytes is a 256-bit DK? How many characters are needed to display 32 bytes in hex? What do these sizes mean for security?
6. **Code review:** identify the flaws in this pseudocode: sharing one salt for all users, `SHA-256(password)`, comparing hashes with `String.equals`, hardcoding keys, and only updating `iterationCount` when upgrading a record.
7. **Production scenario:** if 600,000 iterations take too long under login load, which metrics do you measure and which controls do you add before lowering the work factor? If recommended policy changes a year later, how do you update existing records?
8. **Compatibility:** test passwords with Vietnamese diacritics and combining Unicode characters across two JDK/provider environments; describe how to guarantee identical input bytes, cost, salt, PRF, and DK length.

**Completion criteria:** you can clearly explain why `SecretKeyFactory` + `PBEKeySpec` must use a **random salt, sufficiently large work factor, and bit-denominated key length**, store the required parameters, verify safely, and recognize when PBKDF2 should be replaced by a memory-hard password hashing scheme.

## 12. Authoritative references

- [Java SE 21 – `javax.crypto.SecretKeyFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/SecretKeyFactory.html): obtaining instances, `generateSecret(KeySpec)`, providers, and exceptions.
- [Java SE 21 – `javax.crypto.spec.PBEKeySpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html): constructors, `keyLength` units, password/salt cloning, `clearPassword()`, and notes on password characters.
- [Java SE 21 – `java.security.SecureRandom`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html): cryptographic random source for generating salts.
- [Java SE 21 – Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): `PBKDF2WithHmacSHA256` algorithm name.
- [Java SE 21 – JDK Providers Documentation](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html): PBKDF2 `SecretKeyFactory` support in SunJCE and provider notes.
- [RFC 8018 – PKCS #5: Password-Based Cryptography Specification v2.1](https://www.rfc-editor.org/rfc/rfc8018): PBKDF2 formula, salt, and iteration count.
- [OWASP – Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): choosing Argon2id/scrypt/PBKDF2, salt, pepper, cost, and rehashing.

