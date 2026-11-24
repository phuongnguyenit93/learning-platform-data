# 7.2 Why a Single Fast Hash Is Not Enough for Low-Entropy Passwords

## Objectives

Understand why `SHA-256(password)`, despite using a strong hash algorithm, is **not suitable for storing human-chosen passwords**; analyze offline password-guessing attacks, low entropy, salts, computational cost, and password hashing scheme choices. After this lesson, you will be able to use Java 17 to demonstrate the limits of fast hashing and create/verify PBKDF2 records with salt, iterations, and safe comparison.

## 1. Why isn’t “SHA-256 is very strong” the answer?

SHA-256 is a **cryptographic hash function** with a fixed 256-bit output (32 bytes, 64 hex characters). It is a strong primitive for data integrity and many cryptographic protocols. However, hash functions are designed to compute **efficiently**, whereas password storage requires making **each password guess** resource-intensive.

Consider:

```text
password = a user-chosen secret

stored_hash = SHA-256(password)

To verify:
SHA-256(login_password) == stored_hash ?
```

If the database leaks, an attacker can take `stored_hash` and test passwords on their own hardware. They do not need to “invert” SHA-256. They simply pick a candidate `p`, compute `SHA-256(p)`, and compare it against the leaked hash. The faster the computation, the more candidates they can test in the same amount of time.

There is no new cryptographic flaw in SHA-256 here: **the weakness lies in the input password distribution and how it is used**. Running SHA-512 or SHA3-256 once does not fix that fundamental issue.

| SHA-256 is suitable for | Password storage requires |
| --- | --- |
| Fast, deterministic digests supporting many protocols | **Intentional cost** for every guess |
| Preimage resistance on sufficiently unpredictable inputs | Defense against common-password list attacks |
| Always producing a 256-bit output | Not equating hash output length with input entropy |
| No built-in mandatory salt or work factor | Unique salt, tunable cost, and versioning for upgrades |

**Key takeaway:** a guessable password does not magically become a 256-bit secret just by being hashed to 256 bits.

## 2. What is low entropy?

**Entropy** describes how unpredictable a secret is, based on **how it is generated/chosen** and its probability distribution. If a password is drawn uniformly at random from `N` independent choices, the amount of information in bits is approximately:

```text
H ≈ log2(N) bits
```

For example: a **6-digit PIN generated uniformly at random** has `10^6` possibilities, corresponding to about **19.93 bits**, even though `SHA-256(PIN)` has a 256-bit output.

Users rarely choose uniformly at random. They often use common words, birth years, pet names, keyboard patterns, numeric sequences, patterns like appending `!`, or passwords previously leaked on another service. Candidates are not equiprobable, so attackers can prioritize **high-probability patterns** first.

- A long password can still be weak if it is a very common phrase or predictable pattern.
- Many special characters do not prove high entropy if everyone adds them in predictable spots.
- A multi-word passphrase **drawn independently at random** is usually much harder to guess than a sentence a user invents from familiar context.
- A password manager generating independent random secrets can provide high entropy; password reuse across services destroys that advantage when a breach occurs.

Do not calculate the “exact entropy” of a user password merely by counting letters, digits, and symbols. Entropy depends on the **selection distribution**, not on the hash length or superficial appearance of complexity.

### 2.1 Is preimage resistance broken?

**No.** Preimage resistance describes how hard it is to find an input for a digest in general when the input space is sufficiently large. With human-chosen passwords, an attacker does something much narrower:

```text
candidate_1 -> SHA-256 -> compare with leaked hash
candidate_2 -> SHA-256 -> compare with leaked hash
candidate_3 -> SHA-256 -> compare with leaked hash
...
```

If the second candidate happens to be the password, the attacker has found the password without solving the inverse of SHA-256. Low password entropy makes the **practical guessing space** small and easy to prioritize.

## 3. Offline attack model after a database leak

Suppose a leaked database dump contains these records:

```text
account_id | password_hash
-----------+-------------------------------------
user_a     | SHA-256(password_A)
user_b     | SHA-256(password_B)
```

An attacker obtains this table. From that point on, they do not need to send login requests. They run the algorithm on hardware they control:

```text
Leaked copy of password hashes
                |
                v
Candidate set of common passwords,
previously breached passwords, rule-based variants...
                |
                v
Compute SHA-256(candidate) offline
                |
                v
Compare against hash in database
        /                   \
     match                no match
       |                       |
 found password        try next candidate
```

Factors that favor the attacker:

1. **No request limits from the live system**: CAPTCHAs, account lockouts, and rate limits on the login endpoint cannot block offline trials.
2. **Massive parallelism**: fast hashes compute efficiently on CPUs, GPUs, and specialized hardware.
3. **Data from prior breaches**: dictionaries contain high-probability passwords, avoiding uniform traversal of all possible strings.
4. **Identical passwords produce identical hashes without a salt**: attackers can spot duplicates and reuse work across multiple accounts.

Simplified timing model:

```text
guessing_time ≈ candidates_to_try / attempt_rate
```

This is a conceptual relationship; real-world speed depends on hardware and algorithms. Avoid claiming “an attacker will certainly crack it in X seconds” without measured data. **The cost per guess** is the lever a system can influence using a password KDF with a work factor.

## 4. Unsalted fast hash, salted fast hash, and password KDF

### 4.1 Unsalted

```text
stored = SHA-256(password)
```

Accounts with the same password have the same digest. A precomputed lookup table or dictionary can be reused across accounts. Switching to a single pass of SHA-512 or changing hex to Base64 does not alter this fundamental flaw.

### 4.2 Salted, yet still a fast hash

```text
salt = random_16_bytes()
stored = SHA-256(salt || password)
database = (salt, stored)
```

A **salt** is random bytes **unique to each record** (for instance, 16 bytes via `SecureRandom`), stored alongside the verifier; it **does not need to be secret**.

Salt delivers a crucial benefit: accounts sharing the same password generally get different hashes, reducing the effectiveness of precomputed hash lookup tables and shared computation across accounts.

However, the attacker knows `salt` once the database leaks. They still compute:

```text
SHA-256(account_salt || candidate)
```

for each candidate. That is still a **very fast** SHA-256. Therefore, **a salt is necessary, but not sufficient**.

### 4.3 Salt combined with a dedicated password hashing scheme

```text
stored = PasswordKDF(password, unique_salt, work_factor)
record = (algorithm, version, parameters, salt, stored)
```

Now every trial must execute repeated work or consume memory according to the parameters, rather than a single SHA-256. An attacker can still guess, but **each guess becomes much more expensive**. Salt defeats precomputation and distinguishes records; the KDF raises the cost per candidate. The two roles complement each other.

| Approach | Defeats shared precomputed lookup tables? | Makes each guess expensive? | Suitable for password storage? |
| --- | --- | --- | --- |
| `SHA-256(password)` | No | No | **No** |
| `SHA-256(salt || password)` | Yes, if salt is unique | Negligible | **No** |
| `PBKDF2(password, salt, iterations)` | Yes | Yes, by iteration count | Yes, when properly configured |
| `Argon2id(password, salt, m, t, p)` | Yes | Yes, CPU + memory-hard | Yes, typically preferred for new systems |

**Do not share a single static system-wide salt**, do not use username/time/PID as a salt in place of a CSPRNG, and do not try to hide the salt in source code. Salt differs from a **pepper**, which is an extra secret protected outside the database.

## 5. Practice 1: prove that a salt does not stop offline guessing

This example uses **self-constructed data for educational purposes**. It uses single-pass SHA-256 and two **fixed salts so stdout is reproducible**. Do not copy this salt-generation or verifier-storage pattern into production.

Create **`FastHashGuessDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;

public class FastHashGuessDemo {
    private static byte[] sha256(byte[] salt, String text) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        if (salt != null) {
            digest.update(salt);
        }
        return digest.digest(text.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        String example = "classroom-only";
        byte[] saltA = HexFormat.of().parseHex("00112233445566778899aabbccddeeff");
        byte[] saltB = HexFormat.of().parseHex("ffeeddccbbaa99887766554433221100");

        System.out.println("unsalted repeat equals: " +
                Arrays.equals(sha256(null, example), sha256(null, example)));
        System.out.println("different salts change digest: " +
                !Arrays.equals(sha256(saltA, example), sha256(saltB, example)));

        byte[] stolenHash = sha256(saltA, example);
        String[] dictionary = {"welcome", "password1", "classroom-only", "letmein"};
        int attempts = 0;
        boolean found = false;
        for (String guess : dictionary) {
            attempts++;
            if (MessageDigest.isEqual(stolenHash, sha256(saltA, guess))) {
                found = true;
                break;
            }
        }
        System.out.println("offline guess matched: " + found);
        System.out.println("candidate attempts: " + attempts);
    }
}
```

Compile/run on Java 17 or newer:

```bash
javac --release 17 FastHashGuessDemo.java
java FastHashGuessDemo
```

Verified output:

```text
unsalted repeat equals: true
different salts change digest: true
offline guess matched: true
candidate attempts: 3
```

Result explanation:

- `SHA-256` is deterministic; identical inputs yield identical outputs.
- Two different salts produce different inputs and thus different digests; salt prevents spotting matching hashes and using precomputed tables.
- The simulated attacker knows the **public salt** and the hash, then recomputes each candidate. The third candidate matches, even though the hash is salted.
- `MessageDigest.isEqual` helps compare bytes safely, but it does **not** turn single-pass SHA-256 into a password storage algorithm.

This explains why you need **both a salt and a mechanism that slows down each guess**, rather than merely prepending a string to the SHA-256 input.

## 6. Why must you use a cost-tunable password KDF?

A **password-based key derivation / password hashing scheme** takes a password, salt, and difficulty parameters. It intentionally consumes resources when generating a verifier. A legitimate user normally requires one verification; an attacker trying huge numbers of passwords has that cost multiplied across every attempt.

```text
Registration:
password + fresh_salt + algorithm/params
               |
               v
     PasswordKDF(...)
               |
               v
store {scheme, version, params, salt, verifier}

Verification:
entered password + stored salt/params
               |
               v
     same PasswordKDF(...)
               |
               v
compare verifier -> accept / reject
```

Do not invent a custom “SHA-256 repeated 1,000 times” scheme: standardized password KDFs have vetted designs, parameters, formats, and security details that must be followed.

### 6.1 Key algorithms

| Option | Work factor | Properties | Notes |
| --- | --- | --- | --- |
| **Argon2id** | Memory `m`, passes `t`, parallelism `p` | **Memory-hard**; makes large-scale parallel guessing RAM-expensive | Generally preferred for new systems; requires a maintained library |
| **scrypt** | `N`, `r`, `p` | Memory-hard | Good option if Argon2id is unavailable |
| **bcrypt** | Exponentially scaling cost | Primarily CPU-bound | Legacy systems; watch out for common **72-byte** input limit |
| **PBKDF2-HMAC-SHA256** | `iterations` | Iterated HMAC chain; **not memory-hard** | Standardized, built into Java 17, fits compliance/compatibility needs |
| **Single-pass SHA-256** | No cost | Very fast | Do not use directly to store passwords |

According to the OWASP Password Storage Cheat Sheet, **reference baselines that must be updated over time** include:

- Argon2id: a baseline configuration of **`m=19 MiB, t=2, p=1`**; the guidance also lists equivalent RAM/iteration combinations.
- scrypt: for example `N=2^17, r=8, p=1`.
- bcrypt: cost starting at **10** for legacy compatibility; handle the 72-byte limit carefully.
- PBKDF2-HMAC-SHA256: **600,000 iterations** or more per current OWASP guidance.

These **are not directly comparable numbers** across algorithms (2 passes of Argon2id is not equivalent to 2 iterations of PBKDF2). Benchmark latency, throughput, RAM, and DoS resilience in your production environment; raise costs/rehash as hardware and guidance evolve.

**Memory-hard does not mean uncrackable.** Argon2id forces an attacker to spend more memory resources per candidate; if a password is too common, it can still be guessed. Work factors raise cost; they do not create new entropy for weak passwords.

### 6.2 Why does the Java example below use PBKDF2?

`SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` is a standard Java 17 API. It lets us demonstrate the entire salt/iterations/verifier lifecycle **without external libraries**. PBKDF2 may be required in environments demanding validated/FIPS-compliant implementations; however, if a safe Argon2id library is available and policy allows, OWASP generally prefers Argon2id for new systems.

## 7. Practice 2: complete PBKDF2-HMAC-SHA256 in Java 17

This example uses:

- A **fresh 16-byte salt** generated with `SecureRandom` for every record.
- `PBKDF2WithHmacSHA256` with **600,000 iterations** and a **32-byte** derived hash.
- A storage string `scheme$iterations$Base64(salt)$Base64(derived)` so algorithm and cost are never lost.
- Verification using the **same salt/iterations** stored in the record, followed by byte comparison with `MessageDigest.isEqual`.
- `PBEKeySpec.clearPassword()` and zeroing sensitive arrays owned by the example.
- An iteration cap when parsing records to avoid processing absurdly large configured inputs; **2 million** is a demo policy limit, not a mandatory standard.

Create **`Pbkdf2PasswordDemo.java`**:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class Pbkdf2PasswordDemo {
    private static final String SCHEME = "pbkdf2-sha256";
    private static final int ITERATIONS = 600_000;
    private static final int SALT_BYTES = 16;
    private static final int HASH_BYTES = 32;
    private static final SecureRandom RNG = new SecureRandom();

    private static byte[] derive(char[] password, byte[] salt, int iterations)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(
                password, salt, iterations, HASH_BYTES * 8);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    public static String register(char[] password) throws GeneralSecurityException {
        byte[] salt = new byte[SALT_BYTES];
        RNG.nextBytes(salt);
        byte[] derived = derive(password, salt, ITERATIONS);
        try {
            return SCHEME + "$" + ITERATIONS + "$"
                    + Base64.getEncoder().encodeToString(salt) + "$"
                    + Base64.getEncoder().encodeToString(derived);
        } finally {
            Arrays.fill(derived, (byte) 0);
        }
    }

    public static boolean verify(char[] password, String stored)
            throws GeneralSecurityException {
        String[] parts = stored.split("\\$", -1);
        if (parts.length != 4 || !SCHEME.equals(parts[0])) {
            return false;
        }
        final int count;
        try {
            count = Integer.parseInt(parts[1]);
        } catch (NumberFormatException e) {
            return false;
        }
        if (count <= 0 || count > 2_000_000) {
            return false;
        }
        final byte[] salt;
        final byte[] expected;
        try {
            salt = Base64.getDecoder().decode(parts[2]);
            expected = Base64.getDecoder().decode(parts[3]);
        } catch (IllegalArgumentException e) {
            return false;
        }
        if (salt.length != SALT_BYTES || expected.length != HASH_BYTES) {
            return false;
        }
        byte[] actual = derive(password, salt, count);
        try {
            return MessageDigest.isEqual(expected, actual);
        } finally {
            Arrays.fill(actual, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        char[] correct = "classroom-demo-only".toCharArray();
        char[] incorrect = "classroom-demo-wrong".toCharArray();
        try {
            String first = register(correct);
            String second = register(correct);
            String[] fields = first.split("\\$", -1);
            System.out.println("scheme: " + fields[0]);
            System.out.println("work factor: " + fields[1]);
            System.out.println("salt bytes: " +
                    Base64.getDecoder().decode(fields[2]).length);
            System.out.println("derived bytes: " +
                    Base64.getDecoder().decode(fields[3]).length);
            System.out.println("different salts: " +
                    !fields[2].equals(second.split("\\$", -1)[2]));
            System.out.println("correct password: " + verify(correct, first));
            System.out.println("wrong password: " + verify(incorrect, first));
        } finally {
            Arrays.fill(correct, '\0');
            Arrays.fill(incorrect, '\0');
        }
    }
}
```

Run:

```bash
javac --release 17 Pbkdf2PasswordDemo.java
java Pbkdf2PasswordDemo
```

Verified sample output:

```text
scheme: pbkdf2-sha256
work factor: 600000
salt bytes: 16
derived bytes: 32
different salts: true
correct password: true
wrong password: false
```

Two independently generated 128-bit salts are almost certainly different (the collision probability is minuscule, though not strictly zero). The remaining lines reflect the format and verification results. The program does not print the raw password, salt, or derived hash to the console.

### 7.1 Registration flow explained

1. `register` generates 16 salt bytes via `SecureRandom.nextBytes` **every time a verifier is created**.
2. `PBEKeySpec(password, salt, ITERATIONS, HASH_BYTES * 8)` takes the key length parameter in **bits**, not bytes: 256 bits is solely the verifier length and does not increase the password's entropy.
3. `SecretKeyFactory` performs PBKDF2 with HMAC-SHA256. To use Argon2id, use an appropriate library; do not simply change the algorithm name and expect the built-in Java API to support every KDF.
4. The record contains the scheme, cost, salt, and result. It is a **password verifier**, not an encrypted password that can be decrypted.

### 7.2 Verification flow explained

1. `verify` splits the format and validates scheme/iterations/byte lengths.
2. It uses **the stored record's salt and iterations**, never generating a new salt. Generating a new salt during verification would prevent even the right password from matching.
3. Re-derive using `PBEKeySpec` and compare bytes with `MessageDigest.isEqual`.
4. Return `false` on a wrong password; handle errors and nonexistent-account cases under a unified policy at the application layer.

Capping iterations in the demo prevents malformed records from forcing unbounded work. Production needs additional record/input length limits, encoding validation, request/concurrency limits, and version upgrade policies. **This is instructional code**; real applications should use a maintained password encoder and standard record format.

### 7.3 Passwords in memory

`PBEKeySpec` keeps a copy of the password as a `char[]`, and `clearPassword()` clears **its internal copy**; the caller must still zero its own `char[]` when finished. `Arrays.fill` can shorten how long a secret stays in application-managed arrays, though it does not prove every copy on the heap has been wiped.

Literals like `"classroom-demo-only"` are only for making the demo self-contained; production code must **never hardcode passwords**, never create unnecessary `String` objects, and never write sensitive data to logs, APM, crash reports, or URLs. Immutable `String` instances are hard to erase proactively.

## 8. How to store verifier records so they can be upgraded

If you store only a raw 32-byte string, years later you will not know whether it was SHA-256 or PBKDF2 with how many rounds. Store **version/algorithm/parameters** explicitly in the record, for instance:

```text
{ scheme, version, work_factor, salt, derived_hash }
```

For Argon2id, store `m, t, p`; for bcrypt, store the algorithm's cost/format; for PBKDF2, you need the HMAC algorithm, iteration count, salt, and output length. You can use a **PHC string or library format** instead of inventing your own.

When increasing cost, old verifiers must still verify properly: read the parameters from the record. When a user logs in successfully and the record uses an older cost, use the password just entered to **rehash with a fresh salt and new cost**, and update storage atomically; there is no need to retain plaintext passwords long-term.

**Do not equate “PBKDF2 of an old SHA-256 hash” with PBKDF2 of the original password.** If old fast hashes leaked, attackers can guess them offline; wrapping them in another layer without changing passwords does not undo the exposure. For systems holding legacy SHA-256/passwords, plan a migration:

1. Stop creating new plain SHA-256 verifiers.
2. Support verifying legacy records during a controlled migration window.
3. After a successful login with the original password, generate a new verifier with a dedicated KDF and fresh salt.
4. For accounts that do not log in, require a password reset per policy.
5. If a database leak is suspected, assess the incident, revoke sessions, and reset passwords as needed. Rehashing after an incident **does not make previously cracked passwords safe again**.

## 9. Salt, pepper, encryption, and HMAC: do not confuse their roles

| Mechanism | Secret? | Purpose | Can it replace a password KDF? |
| --- | --- | --- | --- |
| **Salt** | No, stored with record | Defeat precomputation, distinguish each record | No |
| **Pepper** | **Yes**, kept outside DB | Add a barrier if only the database leaks | No |
| **Password KDF** | Password is secret | Make each guess costly in CPU/RAM, produce verifier | This is the component you need |
| **AES encryption** | Must keep encryption key | Protect data that **can be decrypted** with the key | Unsuitable as a normal verifier replacement |
| **HMAC** | Has a key | Authenticate data; can participate in a properly designed pepper scheme | Not for standalone use |

A pepper can live in a vault/HSM/secret manager independent of the database. It **does not replace salt or cost**. If an attacker also obtains the pepper, that defense layer vanishes; pepper rotation requires planning because plaintext passwords are not available for arbitrary recomputation.

Do not store plaintext passwords or encrypt them for recovery if your goal is only **login verification**. Reversible encryption creates the risk of exposing every plaintext password if the key is stolen; password hashing is built for a different requirement.

**Exception note:** a high-entropy, sufficiently long randomly generated token may follow a different threat model. That does not validate using single-pass SHA-256 for low-entropy human passwords.

## 10. Online and offline attacks require different defenses

| Characteristic | Online guessing | Offline guessing |
| --- | --- | --- |
| Data source attacker has | Login endpoint | Copy of verifier/salt/params |
| Sends requests to live system? | Yes | No |
| Do rate limits/CAPTCHA/lockouts help? | Potentially yes | Cannot stop offline computations |
| Does MFA reduce unauthorized logins? | Yes, by design | Does not slow down offline hashing |
| Primary defense | Rate limiting, MFA, monitoring, and anti-enumeration | Salt + password KDF/cost + DB/pepper protection |

A serious system needs both: strong/unique passwords, **common/breached password blocklists**, password manager support, TLS transport security, request limits, appropriate MFA/passkeys, and a standard password KDF.

Avoid **account enumeration** via error messages and large timing disparities; use a unified login error policy. `MessageDigest.isEqual` helps with safer comparisons, but it does not guarantee the **entire login handler** runs in constant time: DB queries, record parsing, KDF computation, and other branches still exist.

## 11. How to choose a work factor

Too low a cost lets attackers test many candidates; too high a cost causes CPU/RAM saturation during concurrent logins, or even DoS. A principled approach:

1. Choose a dedicated KDF, preferring Argon2id when supported; start from configurations in up-to-date security guidance.
2. Benchmark **on production-equivalent infrastructure**, measuring p50/p95/p99 latency, CPU/RAM, and concurrent login volume. With Argon2id, calculate total RAM across concurrent requests.
3. Set CPU/memory budgets, queue/concurrency limits, rate limits, and input length limits.
4. Store scheme/version/work factor per record to scale up over time. Never let untrusted metadata demand billions of iterations.
5. Periodically raise costs as hardware improves; upgrade verifiers during login or password reset flows.

Never “solve” latency by dropping the KDF for single-pass SHA-256. Optimize verification architecture, throughput, and request protections instead.

### 11.1 Unicode and password normalization

Java receives passwords as `char[]`. How the algorithm/provider encodes characters into bytes and applies Unicode rules must remain consistent across registration and verification, and across runtimes/languages if data moves between systems.

- Do not silently lowercase, `trim()`, or truncate passwords.
- If choosing Unicode normalization, specify the exact form/version and apply it consistently.
- Mind the **72-byte** limit in many bcrypt implementations; do not confuse “characters” with “bytes” when inputs include Vietnamese diacritics or emojis.
- Do not treat Base64/hex as a security enhancement: those are just encodings.

In production, pick a vetted library password encoder rather than writing unnecessary custom password hashing/migration variants.

## 12. Common misconceptions

- **“SHA-256 is 256 bits, so the password has 256-bit security.”** False. A long output creates no entropy for a weak password.
- **“Adding a salt is enough.”** False. Salt defeats precomputed tables, but you still need a password KDF.
- **“Looping SHA-256 a few times is equivalent to Argon2id.”** False. Do not roll your own scheme; Argon2id provides memory-hardness and peer-reviewed design.
- **“Hashes are one-way so nobody can get the password.”** False. Dictionary attacks only need the hash and candidates, not function inversion.
- **“Rate limits block offline brute force.”** False. Offline guessing runs outside your server.
- **“Lots of special characters guarantee high entropy.”** False. User patterns can still be predictable.
- **“Salt must be secret; pepper can live right in the DB.”** The opposite: salt is public, while pepper must be protected outside the DB.
- **“Hashing a password twice with two fast algorithms is secure.”** Neither provides enough computational cost or memory-hardness to protect weak passwords.
- **“MFA means stored password hashes don’t need protection.”** False. MFA is an added login layer; database leaks remain dangerous, especially due to password reuse.
- **“Converting old hashes to a new format resolves the breach.”** False. Old passwords may already have been cracked; investigate and reset/revoke sessions as warranted.

## 13. Self-check exercises

**Question 1.** How many bits of entropy does a uniformly random 6-digit PIN have before SHA-256 hashing?  
**Answer:** Roughly **19.93 bits**, not 256 bits.

**Question 2.** Why isn’t an offline attacker stopped by CAPTCHA?  
**Answer:** They compute verifiers themselves from leaked data without calling the login endpoint.

**Question 3.** What does giving two accounts with the same password different salts solve?  
**Answer:** It distinguishes records, reduces precomputed table effectiveness, and prevents hash reuse across accounts; it **does not** stop an attacker from testing candidates against a known salt.

**Question 4.** How does PBKDF2 differ from single-pass SHA-256?  
**Answer:** PBKDF2 uses a salt and an `iterations` work factor so every guess runs many HMAC rounds. It is not memory-hard like Argon2id.

**Question 5.** Why not generate a new salt every time a user logs in to compare?  
**Answer:** Verification must use the salt saved at registration and rerun the KDF on the entered password. A new salt is generated only when creating a **new verifier/rehash**.

**Question 6.** What is a pepper?  
**Answer:** An additional server-side secret stored outside the DB; it does not replace salt or password KDF.

**Question 7.** If an old verifier used 20,000 PBKDF2 iterations and the new policy requires 600,000 iterations, how should you handle it?  
**Answer:** Verify using the old parameters; once the user logs in successfully, rehash from the entered password with a new salt/new cost and store the record with updated metadata.

**Question 8.** In a breach of SHA-256 password hashes, does merely replacing existing hashes with `SHA-256(SHA-256(password))` solve the problem?  
**Answer:** No. It still lacks a dedicated scheme and fails to safely remediate passwords attackers may already have recovered.

## Model summary

```text
Human-chosen passwords: typically low entropy
                 |
                 v
Single-pass SHA-256: testing candidates is cheap
                 |
                 v
If verifier leaks, attacker guesses offline

The right defense:
Unique CSPRNG salt + cost-tunable password KDF
                 |
       +---------+-----------+
       |                     |
   Argon2id/scrypt       PBKDF2/bcrypt
   CPU + memory          round-based cost
       |                     |
       +---------+-----------+
                 |
                 v
Store {scheme/version/params/salt/hash}
                 |
                 v
Login: KDF with stored salt + safe comparison
                 |
                 v
Combine with rate limiting, MFA, and upgrade management
```

**Hash length does not make a weak password harder to guess.** To protect password verifiers when a database is stolen, make **every candidate** expensive to test, add an independent salt, and scale cost over time.

## Official references

- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): Argon2id, scrypt, bcrypt, PBKDF2, salt/pepper, and verifier upgrades.
- [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): offline-resistant verifiers, salts, and appropriate cost.
- [Java 17 PBEKeySpec API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html): `char[]`, salt, iterations, key length, and `clearPassword()`.
- [Java 17 SecretKeyFactory API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html): factory for key derivation mechanisms.
- [Java 17 SecureRandom API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): generating salts with a cryptographic random generator.
- [Java 17 MessageDigest API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 and `isEqual`.
