# 7.5 Creating, Storing, and Verifying Password Records with Full Parameters

A Java application must never store passwords in plaintext, in decryptable encrypted form, or as fast single-pass hashes such as `SHA-256`. When a database leaks, an adversary can test massive numbers of passwords offline. The goal of **password hashing / password-based key derivation** is to produce a **password verifier** that is expensive to guess by using a dedicated high-cost algorithm, a **unique random salt**, and **fully stored parameters**.

This lesson focuses on the **lifecycle of a password record**: creating the record on registration/password change, storing it in the right format, reading and verifying it on login, detecting records that need upgrading, and handling invalid data/configurations. The Java 17+ example uses **PBKDF2WithHmacSHA256** built into the JDK so it compiles standalone. When a system has a suitable maintained library, **Argon2id** is usually the preferred choice for passwords due to its memory-cost mechanism; later sections explain its corresponding parameters in full.

## 1. What is a password record?

A password record is the **data needed to verify an entered password without storing the original password**. It is not just a raw hash string. A practical design must unambiguously identify the algorithm, parameters, salt, and derived value; it may also need a version to read legacy records after upgrades.

~~~text
On account creation / password change:
    password + random salt + algorithm + cost parameters
                            |
                            v
                 KDF / password hasher
                            |
                            v
            derived verifier + metadata
                            |
                            v
       store PASSWORD_RECORD in database

On login:
    user-entered password + metadata/salt from PASSWORD_RECORD
                            |
                            v
              run same KDF and parameters
                            |
                            v
         compare verifier appropriately
                            |
                 valid / invalid password
~~~

The salt **does not need to be secret** and is usually stored with the record. The derived value is not the original password either, yet it is sensitive security data: anyone who can read the database can perform offline password guessing. Control access permissions, backups, and data exports.

### How does password hashing differ from other mechanisms?

| Mechanism | Purpose | Use for storing login passwords? |
| --- | --- | --- |
| Single-pass SHA-256 | Compute fast data fingerprints | **No.** High speed lets attackers test massive password lists. |
| Single-pass HMAC-SHA256 | Authenticate messages with a secret key | **Not sufficient alone.** Lacks dedicated cost to resist offline guessing. |
| AES-GCM | Encrypt data decryptable with a key | **Not the primary mechanism for password verifiers.** Recovering the original password is unnecessary. |
| PBKDF2-HMAC-SHA256 | Iterated, salted derivation | **Usable** with calibrated cost configuration and proper bounds. |
| Argon2id | Password hashing with tunable CPU and memory cost | **Preferred when a suitable library is available**, properly configured and tested. |
| bcrypt / scrypt | Dedicated password hashing algorithms | Usable when fitting requirements; understand length/encoding limits and parameters. |

**Never “decrypt” a password hash at login.** The server repeats the derivation with the newly entered password and checks the result.

## 2. Threats and protection boundaries

Suppose a database table of account names and password records is copied. An adversary can pick trial passwords, take the salt/params from the record, and compute hashes offline to guess. **The more CPU/memory each trial consumes, the costlier guessing becomes**, though no algorithm turns an overly common password into an unguessable secret.

Controls needed together:

1. A strong password hasher, reasonable work factor, and an independent random salt per record.
2. Suitable password policy and login flow; block common/breached passwords and support MFA where warranted.
3. Rate limiting, credential-stuffing detection, and controlled lockouts/backoff **at the online login step**.
4. Restricted read access to password records, encrypted backups where needed, and operational secret protection.
5. Secure flows for password reset, password change, hash upgrades, and session management.

**Rate limiting does not slow offline attacks against a stolen database.** Conversely, a very slow KDF does not by itself protect an endpoint from request floods; calibrate login capacity and concurrency limits.

## 3. What parameters does a complete record need?

Never rely on defaults hardcoded in currently running code to interpret a record created by an older version. Essential parameters must travel with the record or be referenced stably via a **format version**.

| Attribute | Meaning | PBKDF2 / Argon2id example |
| --- | --- | --- |
| **Format version** | How to parse the record, encoding policy, preprocessing, algorithm layout | `p1` or a versioned Argon2id profile. |
| **Algorithm** | Exact password hashing/KDF algorithm | `PBKDF2WithHmacSHA256` / `Argon2id`. |
| **Internal PRF / hash** | Underlying primitive inside the KDF when required | `HMAC-SHA-256` for PBKDF2; do not infer solely from the name “PBKDF2”. |
| **Salt** | Independent random bytes, typically ≥16 bytes for new designs | 16 bytes generated by `SecureRandom`, stored as Base64url. |
| **Work factor** | Algorithm-specific cost | PBKDF2: iteration count; Argon2id: memory `m`, passes `t`, parallelism `p`. |
| **Derived output length** | Bit/byte length of the derived verifier | 256 bits = 32 bytes in the PBKDF2 example. |
| **Hash/verifier** | Stored derived value for comparison | Binary bytes encoded as Base64/PHC format. |
| **Representation format** | Field ordering rules, delimiters, Base64, version, and parser | Delimited string or explicit JSON/columns. |
| **Pepper key version** (if used) | Identifies an extra secret outside the database to support rotation | Key reference ID; **never store the pepper itself** in the password record. |

Salt, iteration count, hash algorithm, and hash length **are not the password** and may be stored with the record. Never store or log plaintext passwords; never embed the pepper secret inside the record either.

### 3.1. Application PBKDF2 schema example

This lesson uses an application-defined format:

~~~text
p1$PBKDF2WithHmacSHA256$600000$256$SALT_BASE64URL$VERIFIER_BASE64URL
 |              |              |    |          |                 |
version      algorithm      rounds bits     salt bytes      derived bytes
~~~

The line above is a **field diagram**, not a valid computed record value. When running the Java demo, `SALT_BASE64URL` and `VERIFIER_BASE64URL` are replaced with actual Base64url values, differing on each record creation.

Meaning:

- **p1:** schema version 1. The parser must know which algorithm `p1` uses, how password characters map to KDF input, salt and output lengths, and allowed encodings.
- **PBKDF2WithHmacSHA256:** standard algorithm name used by the JDK; HMAC-SHA256 is the internal PRF of PBKDF2.
- **600000:** 600,000 iterations belonging to that specific record. Never pull 600,000 from a “current default” variable when verifying an old 200,000-round record.
- **256:** number of output **bits**; 256 bits = 32 bytes. Do not confuse this bit count with password entropy.
- **Salt:** 16 randomly generated bytes for that record creation.
- **Verifier:** 32 bytes derived from password + salt + parameters, Base64url-encoded for storage in a text field.

**Never store a `String` password in the record.** Every new record must have a new salt even if the user re-enters the exact same old password.

### 3.2. Storage options

You can store the full versioned record in a suitably sized `VARCHAR`/`TEXT` column, or split fields (`algorithm`, `iteration_count`, `salt`, `verifier`, `version`) into typed database columns. Both approaches are valid provided that:

- There is a stable **format contract**, validating length/encoding and never truncating Base64 characters.
- Persisting on registration/password change is **atomic**, avoiding mixing a new salt with an old verifier.
- Unique account keys and database access controls are enforced.
- There is a plan to read legacy records when upgrading algorithm, version, or work factor.
- The hash is never used as a login token or public account identifier.

Base64 field length is measured in **characters**, whereas salt/verifier length is measured in **bytes**. For example, 16 salt bytes encoded in unpadded Base64url are typically 22 characters, and a 32-byte verifier is typically 43 characters. The parser must decode and check actual byte lengths.

## 4. Choosing algorithms and parameters: no single default for all environments

The OWASP Password Storage Cheat Sheet recommends Argon2id where suitably supported and suggests meaningful minimum configurations such as **m=19456 KiB (19 MiB), t=2, p=1**. Argon2id has **memory (`m`)**, **passes (`t`)**, and **parallelism (`p`)** parameters; benchmark them in your real environment. Increasing `p` does not multiply iteration passes and does not automatically multiply memory `m`.

For PBKDF2-HMAC-SHA256, OWASP cites **600,000 iterations** in FIPS-related guidance; the Java example uses this baseline while still requiring benchmarks for CPU, login traffic, timeout limits, and actual compliance needs. **Security parameters are versioned decisions**, not immutable eternal constants.

| Algorithm | Parameters that must be kept | How to evaluate |
| --- | --- | --- |
| PBKDF2-HMAC-SHA256 | PRF, iterations, salt, output length, encoding | Benchmark verify latency on target runtime and hardware; bound iterations in the parser. |
| Argon2id | variant, version (typically v=19), `m` KiB, `t`, `p`, salt, output length | Benchmark RAM and CPU per verify, total concurrency, memory exhaustion, and limits. |
| scrypt | `N`, `r`, `p`, salt, output length | Evaluate memory, CPU, and per-request limits. |
| bcrypt | variant/prefix, cost, salt, and library-formatted hash string | Check password byte limits, encoding handling, and cost-upgrade path. |

Prefer a maintained password-hashing library with complete format/encoder/verify APIs. Do not build your own hashing by manually looping SHA-256. Password hashing algorithms must be implemented and evaluated according to standards, not cobbled together from arbitrary primitives.

## 5. Creating a new record on registration or password change

A record-creation flow should follow this order:

1. Receive the password over HTTPS, check registration policies, and enforce reasonable size limits to prevent excessive resource consumption.
2. If there is a **Unicode normalization** rule, define it explicitly (e.g., NFC), apply it **consistently** at creation and verification, and tie it to the format version. Never silently trim/lowercase passwords without an explicit policy.
3. Select the **current algorithm/profile** from server configuration; never let the browser specify the algorithm or lower the work factor.
4. Generate a **fresh salt with `SecureRandom`**, independent of user ID, email, timestamp, or password. Generate a distinct salt on every password change.
5. Run the password hasher with the salt and **full profile parameters**; obtain verifier bytes.
6. Package version, algorithm, iterations (or `m`/`t`/`p`), salt, output length, verifier, and key version if using a pepper.
7. Store **atomically** with the account record under application privileges; never write plaintext passwords or derived keys to logs.
8. Limit the lifetime of temporary passwords and verifiers in memory where possible; clear application-owned `char[]`/`byte[]` buffers once no longer needed.

Distinct salts ensure two users with the same password generally get different verifiers while preventing direct use of shared precomputed hash tables. **Salt does not replace work factor**, does not need to be hidden, and is not the same as a pepper.

## 6. Verifying a record: use the exact stored parameters

At login, **never** simply call the KDF with the application's current parameters and compare. Read the parameters from the record to verify legacy records properly.

~~~text
Account + candidate password
             |
             v
Look up password record by account
             |
             v
Parse version + algorithm + params + salt + verifier
             |
      validate allowlist, bounds, lengths
             |
       invalid -> reject
             |
             v
KDF(candidate, storedSalt, storedParams)
             |
             v
Compare bytes with storedVerifier
        |                |
      match           mismatch
        |                |
        v                v
Check for upgrade      reject
        |
        v
Authenticate + manage session per policy
~~~

Key points:

- **Select the algorithm via a trusted allowlist and version**, never letting a stored string or user input trigger arbitrary algorithms or cost values.
- **Read the stored salt**, never generating a new salt during verification; a new salt yields a different output.
- **Use the record's iterations/`m`/`t`/`p`**, not the new policy work factor on an old record.
- **Validate lengths and upper bounds** before running the KDF. A tampered record claiming “999,999,999 iterations” can hang the endpoint or cause denial of service.
- **Compare the entire derived verifier** with a suitable comparison such as `MessageDigest.isEqual` on fixed-length arrays; avoid prefix or string comparisons that may leak timing information.
- **Mark the user authenticated only after verification succeeds**; rehashing and session issuance must happen after this step.
- **Distinguish corrupted-record errors from wrong passwords in internal logs**, while keeping external responses generic to limit user enumeration or cryptographic oracle leaks.

`MessageDigest.isEqual` only limits timing dependence on **byte contents** under appropriate conditions; it does not make the entire endpoint constant-time because lookup, decoding, KDF, network, and error paths still vary in duration.

## 7. Java 17+: create, serialize as string, verify, and check rehash need

The standalone example below uses **`SecretKeyFactory`**, **`PBEKeySpec`**, **`SecureRandom`**, Base64url, and **`MessageDigest.isEqual`**. It creates two records with different parameters, verifies right/wrong passwords, detects legacy records needing rehash, and checks iteration bounds before running the KDF.

For illustration, profile **`p1`** supports only PBKDF2-HMAC-SHA256, exact 16-byte salts, exact 32-byte verifiers, and iterations in **100,000–2,000,000**, with **600,000** as the current cost. That range is **the demo's parsing rule**, not a recommendation to create new records at 100,000; the public creation path uses 600,000. The historical record at 200,000 is solely to illustrate migration.

Save as **PasswordRecordDemo.java**:

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class PasswordRecordDemo {
    private static final String VERSION = "p1";
    private static final String ALGORITHM = "PBKDF2WithHmacSHA256";
    private static final int CURRENT_ITERATIONS = 600_000;
    private static final int MIN_ALLOWED_ITERATIONS = 100_000;
    private static final int MAX_ALLOWED_ITERATIONS = 2_000_000;
    private static final int SALT_BYTES = 16;
    private static final int KEY_BITS = 256;
    private static final int KEY_BYTES = KEY_BITS / 8;
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder DECODER = Base64.getUrlDecoder();

    private record Parsed(int iterations, byte[] salt, byte[] expected) {}

    public static String create(char[] password) throws GeneralSecurityException {
        return createAtCost(password, CURRENT_ITERATIONS);
    }

    private static String createAtCost(char[] password, int iterations)
            throws GeneralSecurityException {
        requirePassword(password);
        checkIterations(iterations);
        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);
        byte[] derived = derive(password, salt, iterations);
        try {
            return String.join("$", VERSION, ALGORITHM,
                    Integer.toString(iterations), Integer.toString(KEY_BITS),
                    ENCODER.encodeToString(salt), ENCODER.encodeToString(derived));
        } finally {
            Arrays.fill(derived, (byte) 0);
        }
    }

    public static boolean verify(char[] candidate, String stored)
            throws GeneralSecurityException {
        requirePassword(candidate);
        Parsed p = parse(stored);
        byte[] actual = derive(candidate, p.salt(), p.iterations());
        try {
            return MessageDigest.isEqual(p.expected(), actual);
        } finally {
            Arrays.fill(actual, (byte) 0);
        }
    }

    public static boolean needsRehash(String stored) {
        Parsed p = parse(stored);
        return p.iterations() < CURRENT_ITERATIONS;
    }

    private static byte[] derive(char[] password, byte[] salt, int iterations)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, KEY_BITS);
        try {
            SecretKeyFactory factory = SecretKeyFactory.getInstance(ALGORITHM);
            return factory.generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    private static Parsed parse(String stored) {
        if (stored == null || stored.length() > 256) {
            throw new IllegalArgumentException("Malformed password record");
        }
        String[] parts = stored.split("\\$", -1);
        if (parts.length != 6
                || !VERSION.equals(parts[0])
                || !ALGORITHM.equals(parts[1])
                || !Integer.toString(KEY_BITS).equals(parts[3])) {
            throw new IllegalArgumentException("Unsupported password record");
        }
        final int iterations;
        try {
            iterations = Integer.parseInt(parts[2]);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("Bad iteration count", e);
        }
        checkIterations(iterations);
        final byte[] salt;
        final byte[] expected;
        try {
            salt = DECODER.decode(parts[4]);
            expected = DECODER.decode(parts[5]);
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("Bad Base64url", e);
        }
        if (salt.length != SALT_BYTES || expected.length != KEY_BYTES
                || !ENCODER.encodeToString(salt).equals(parts[4])
                || !ENCODER.encodeToString(expected).equals(parts[5])) {
            throw new IllegalArgumentException("Invalid salt or verifier encoding");
        }
        return new Parsed(iterations, salt, expected);
    }

    private static void checkIterations(int count) {
        if (count < MIN_ALLOWED_ITERATIONS || count > MAX_ALLOWED_ITERATIONS) {
            throw new IllegalArgumentException("Iteration count out of policy");
        }
    }

    private static void requirePassword(char[] chars) {
        if (chars == null || chars.length == 0) {
            throw new IllegalArgumentException("Missing password");
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password = "A long example password".toCharArray();
        char[] wrong = "A different password".toCharArray();
        try {
            String saved = create(password);
            System.out.println("Record field count: " + saved.split("\\$", -1).length);
            System.out.println("Correct password: " + verify(password, saved));
            System.out.println("Wrong password: " + verify(wrong, saved));
            System.out.println("Current record needs upgrade: " + needsRehash(saved));

            String old = createAtCost(password, 200_000);
            System.out.println("Legacy record verifies: " + verify(password, old));
            System.out.println("Legacy record needs upgrade: " + needsRehash(old));

            String[] fields = saved.split("\\$", -1);
            fields[2] = "999999999";
            boolean rejected = false;
            try {
                verify(password, String.join("$", fields));
            } catch (IllegalArgumentException expected) {
                rejected = true;
            }
            System.out.println("Out-of-bounds parameter rejected: " + rejected);
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
~~~

Compile with JDK 17+ and run:

~~~bash
javac --release 17 -encoding UTF-8 PasswordRecordDemo.java
java PasswordRecordDemo
~~~

Reliable output:

~~~text
Record field count: 6
Correct password: true
Wrong password: false
Current record needs upgrade: false
Legacy record verifies: true
Legacy record needs upgrade: true
Out-of-bounds parameter rejected: true
~~~

Because actual salt/hash values are not printed, stdout remains reproducible across runs even though each execution generates a different salt and verifier. The record has **six fields**: version, algorithm, iterations, output bits, Base64url salt, and Base64url derived bytes. In the demo, passwords are string literals so the program runs standalone; real applications receive them from requests and should avoid creating extra unnecessary `String` copies.

### Explaining the Java components

- **`SecureRandom`** generates a fresh 16-byte salt in `createAtCost`. Never use `java.util.Random`, `currentTimeMillis`, or email addresses as salts.
- **`PBEKeySpec(password, salt, iterations, KEY_BITS)`** packages the exact PBKDF2 inputs. **`KEY_BITS` is the output bit length**, not the iteration count.
- **`SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")`** retrieves the KDF implementation from the provider; **`generateSecret(spec).getEncoded()`** extracts the 32 derived bytes in a provider compatible with this example.
- **`PBEKeySpec.clearPassword()`** clears the `char[]` copy inside the key spec. The caller remains responsible for clearing its input `char[]` when finished; that is why `main` uses **`Arrays.fill`**. Clearing does not guarantee every copy in the JVM/HTTP stack vanishes immediately.
- **Unpadded Base64url** is solely a text format for storing bytes; it is not secret encryption and adds no password strength.
- **`parse()`** checks exact version, algorithm name, output bits, field count, iteration bounds, salt/verifier byte lengths, and canonical Base64url before running expensive computation.
- **`MessageDigest.isEqual`** compares all 32 verifier bytes. Because the parser fixes the output size, there is no “match first n bytes” flaw.
- **The demo's `needsRehash()`** checks the old iteration count against the new configuration. When deploying multiple algorithms/versions, extend this check to inspect algorithm, params, output length, salt policy, and format version.

**Example boundaries:** the program does not implement HTTP endpoints, DB transactions, MFA, pepper, account lockout, multiple historical schemes, or optional Unicode normalization. Those responsibilities belong to the authentication service and are explained below.

### Why must `parse` check bounds?

A record claiming 2,000,000,000 iterations, a decoded salt megabytes long, or a verifier other than 32 bytes can exhaust CPU/RAM if passed straight into the KDF. The parser validates **string length**, **algorithm/version allowlist**, **iteration minimum/maximum**, and **decoded byte sizes** before doing work.

`MAX_ALLOWED_ITERATIONS` in code is a **deployment policy that must be updated deliberately**. Never let a value from a user request override it. If a system holds legacy records with out-of-policy parameters, handle them through a dedicated migration path rather than disabling checks or accepting arbitrary values.

## 8. Connecting the example to a database

A service might store records like this:

~~~text
users
----------------------------------------------
id               BIGINT / UUID
email            VARCHAR UNIQUE
password_record  VARCHAR / TEXT
password_changed_at TIMESTAMP
record_version   INTEGER (if optimistic locking is needed)
----------------------------------------------
~~~

**`password_record`** holds sufficient metadata for verification. The **`password_changed_at`** column serves session management and operational history per policy; never use it as a salt. **`record_version`** coordinates DB updates and is completely distinct from format version `p1` inside the password record content.

### Registration

1. Validate account, password policy, and email verification per application rules.
2. Call `create(password char[])` to generate salt and derived verifier.
3. Persist the new record with the user inside a transaction; write an audit event containing no password, verifier, or secrets.
4. Clear owned password buffers in `finally`; keep them out of access logs and exceptions.

### Login

1. Look up the user by identity, applying rate limiting and anti-guessing controls.
2. If a valid record exists, call `verify(candidate, storedRecord)`.
3. When `verify` returns `true`, continue account-status checks, MFA if needed, session creation, and login metadata updates.
4. If the record is weaker than current policy, generate a new record **with a fresh salt and current parameters** after successful verification; update the database using a version/compare-and-swap condition.
5. If `verify` returns `false` or the record is malformed, issue no session; return a generic response to limit user enumeration.

### Changing and resetting passwords

Never “decode the hash back to the old password.” After authenticating/authorizing the change or reset flow, create a **brand-new record** with a fresh salt, parameters, and verifier, update atomically, and revoke sessions/tokens per policy. Never reuse the old record or old salt just because the user entered the same password.

## 9. From PBKDF2 to Argon2id: records with m, t, p

When using Argon2id, besides algorithm and salt/hash, the record must contain **algorithm version, memory cost, time cost, parallelism, and output length**. A common representation is the **PHC string format**, conceptually structured as:

~~~text
$argon2id$v=19$m=19456,t=2,p=1$<encoded salt>$<encoded hash>
~~~

This illustrates the format so you recognize its fields, **not a valid hash to copy for verification**. For Argon2id:

- **`argon2id`** identifies the variant suitable for password hashing.
- **`v=19`** indicates the Argon2 algorithm version (decimal 19 corresponds to version `0x13`).
- **`m=19456`** is total memory used in computation, **in KiB**, equivalent to 19 MiB.
- **`t=2`** is the number of passes, **not 2 seconds**.
- **`p=1`** is the number of lanes/parallelism; it does not mean each lane receives `m` KiB separately, since `m` is the total.
- **`salt` and `hash`** must store all bytes; in PHC format, libraries typically encode them with unpadded Base64 per format convention.
- **Output length** can be inferred from the hash bytes in the format, yet must still be specified and validated by your profile/library.

Java 17 does not guarantee a default Argon2id `SecretKeyFactory` engine across every JDK. Use a trusted, actively maintained password-hashing library providing **`hash(password, params)`** / **`verify(encoded, password)`** and PHC parsing. Never implement Argon2id by hand from SHA/bitwise operations.

**Migrating between algorithms:** when moving from PBKDF2 to Argon2id, retain verification support for permitted valid PBKDF2 records; after a successful login, rehash with Argon2id and a fresh salt, then replace the record atomically. You cannot convert a PBKDF2 hash into an Argon2id hash **without knowing the password**; the old hash is not a valid password input for the new hash.

## 10. Upgrading parameters and schemas without breaking login

Password hashing costs need an upgrade path over time. As CPUs/GPUs and cracking capabilities improve, today's profile can become weak. **Self-describing records** let you verify old records and **rehash on successful login**.

~~~text
User enters password
        |
        v
Verify with stored record's algorithm + params + salt
        |
     succeeded?
      /       \
    No        Yes
     |         |
    Reject     v
        Does record meet current profile?
                /         \
              Yes          No
              |              |
        Auth session    Generate fresh salt + hash with new profile
                               |
                               v
                    Update atomically if old record
                    is still the stored version
                               |
                               v
                       Auth session
~~~

### Key migration rules

1. **Upgrade only after verifying the original password**; never treat the stored hash as the new password.
2. **The new profile must be configured server-side**; never trust parameters sent by the client.
3. **Generate a fresh salt** and compute a complete new record; never edit only the `iterations` field while keeping the old verifier.
4. **Avoid race conditions:** two concurrent logins or a login racing with a password reset can contend on updates. Use optimistic locking/compare-and-swap on the record version or hash of the old value per DB policy so a newer record is not overwritten.
5. **Never downgrade:** if a record already has a stronger cost/algorithm than an older node's profile, do not overwrite it with the weaker profile.
6. **For long-inactive accounts**, on-login migration will not update them promptly; you may need a communication or password-reset plan.
7. **Keep legacy verifiers for a bounded period** during transition if policy permits, tracking supported algorithms/params; never retain weak legacy formats indefinitely without a security decision.

### When normalization or encoding must change

Rules for handling Unicode password characters are **part of the format contract**. Switching from “no normalization” to “Unicode NFC” can change the derived input bytes. Never change preprocessing while verifying old records and inadvertently reject all legacy accounts. Tie normalization policy to the version and migrate when the original password is available at login.

With PBKDF2 via Java `PBEKeySpec`, how the provider interprets `char[]` as byte input must be tested in your target deployment environment, especially for passwords with Vietnamese diacritics, non-ASCII characters, and combining marks. Standardize encoding/normalization in the protocol; never convert passwords to bytes arbitrarily or substitute a `String` with an unclear charset or silent `trim`.

## 11. Salt, pepper, and where secrets live

### 11.1. Salt

A salt is a **non-secret random value** ensuring identical passwords yield different hashes and thwarting precomputed lookup tables. A salt must be:

- Generated by **`SecureRandom`** or an equivalent cryptographic RNG.
- Fresh for **every record / every password change**, never a single application-wide salt.
- Long enough to make collision probability negligible; e.g., 16 bytes (128 bits).
- Stored alongside the record for reuse during verification; never changed during verification.

Never use user ID, email, username, or timestamps as your primary salt source; they are predictable, lack cryptographic randomness, and can collide.

### 11.2. Pepper

A pepper is an **additional secret** managed **separately from the password-record database**, e.g., in a KMS/HSM or access-controlled secret manager. It provides defense in depth when only the database leaks while the pepper management system remains intact.

- **Never store the pepper inside `password_record`**, never commit it to source control, and never log it.
- If using a pepper, design the exact combination point with the password hash (such as a post-hash HMAC per reviewed policy); never casually concatenate strings and call it safe peppering.
- You may store a non-secret **pepper key ID** to locate the right secret at verification time; rotation works differently from salt.
- Losing the pepper can make old passwords unverifiable; leaking the pepper requires incident response/rotation and potentially password resets depending on architecture.
- Pepper does not replace a memory-hard/slow algorithm, per-record salts, or MFA.

The Java example in section 7 **omits a pepper** to keep the core problem transparent and self-contained.

## 12. Invalid inputs and error handling

A corrupted record or one imported from a legacy system may miss fields, have a truncated salt, specify an unknown algorithm, or carry an invalid iteration count. **Fail fast** and never attempt heuristic repairs on authentication data.

| Error condition | What the system should do |
| --- | --- |
| Missing format version or unsupported version | Reject with an appropriate internal operational reason; do not exhaustively try unbounded parsers. |
| Algorithm outside allowlist | Reject; never fall back to MD5/SHA-1 or fast hashes. |
| Iterations = 0 / negative / above max | Reject **before running PBKDF2**, preventing DoS. |
| Argon2 `m`/`t`/`p` excessive or invalid | Reject against profile/bounds before heavy RAM/CPU work. |
| Empty, too-short, truncated, or malformed salt encoding | Reject; never generate a new salt to “recover” an old record. |
| Verifier missing bytes / mismatched output length | Reject; never compare a prefix or ignore missing bytes. |
| Wrong password | KDF yields different bytes and verify returns false; issue no session. |
| Nonexistent or disabled user | Handle consistently with rate limiting, avoiding account enumeration. |
| Provider lacks algorithm or configuration | Handle as controlled system error and alert operations; never silently lower security level. |

**A record is untrusted input that must be validated even when read from your database.** It can be corrupted by migrations, bugs, manual admin edits, or swapped/tampered data. Upper bounds on iterations, output length, and envelope size are essential to prevent resource abuse.

### Wrong passwords and response timing

A proper byte-array comparison **does not guarantee the entire endpoint responds in constant time**. DB lookup, parsing, KDF, MFA, and rate limiting all take varying times. You need an anti-enumeration policy, real-world observability, rate limiting, and generic error messages; do not try to force an entire system into constant time with arbitrary `sleep` calls.

## 13. Memory safety and handling sensitive data in Java

**`char[]`** is often preferable to `String` for accepting passwords in APIs that let the caller control the buffer: you can call **`Arrays.fill(password, '\0')`** when finished. **`PBEKeySpec.clearPassword()`** clears the internal copy inside the key spec. However:

- HTTP frameworks, JSON parsers, logging, or other libraries may already have created `String` objects or separate buffers; clearing one `char[]` **does not prove** every copy was erased.
- Never print passwords, tokens, peppers, or derived verifiers to logs, traces, error pages, metric labels, or telemetry.
- Never use passwords or salts as long-lived `Map`/cache keys; avoid keeping passwords alive unnecessarily across threads or async tasks.
- Temporary **derived verifier `byte[]` buffers** should be zeroed after use where feasible. The hash belongs in long-term database storage, not lingering in multiple memory copies.
- Never use `String.equals` to compare text-encoded verifiers; decode to exact-length bytes and use an appropriate comparison.
- Initialize `SecretKeyFactory`/`PBEKeySpec` per use as needed; never share mutable password buffers across concurrent requests.

**Note:** printing field counts and `true`/`false` results in the demo is safe for learning; in production, never write record contents into access logs, even though hashes are not plaintext.

## 14. Comprehensive testing for password records

| Test case | Setup | Expected result |
| --- | --- | --- |
| Create new record | Valid password, current profile | Contains version/algorithm/params/salt/verifier; random salt; record parses cleanly. |
| Correct password | Newly created record + same password | Verify returns true. |
| Wrong password | Same record + different password | Verify returns false. |
| Recreate with same password | Two `create` calls on same string | Salts differ with overwhelming probability, verifiers differ, both verify the password. |
| Wrong salt | Flip one byte of salt in record while keeping verifier | Verify returns false or rejects via format checks. |
| Wrong verifier | Flip one byte of stored derived hash | Verify returns false. |
| Missing field | Truncate record or drop delimiter | Reject before KDF. |
| Malformed Base64url | Invalid characters or padding for profile | Reject; do not silently normalize. |
| Zero iterations | Invalid PBKDF2 cost record | Reject before KDF. |
| Huge iterations | `999999999` | Reject before KDF, preventing CPU exhaustion. |
| Different output length | Record claims 256 bits but hash lacks bytes | Reject; do not prefix-compare. |
| Legacy profile | 200,000-iteration record in allowed range | Verify still succeeds, `needsRehash=true`. |
| Current profile | 600,000-iteration record | Verify succeeds, `needsRehash=false`. |
| Concurrent login | Two simultaneous logins / parameter upgrades | No inconsistent DB state or overwritten password resets. |
| Unicode | Diacritics, emojis, combining marks per policy | Consistent create/verify round-trip under same encoding and normalization. |
| Rehash + failed password | Wrong password on legacy record | Database record remains unchanged. |
| Rehash + successful password | Valid password on legacy record | New record uses fresh salt and new profile, updated atomically. |

You do not need a two-run unit test to “prove salts never collide”; with 128-bit salts, practical assurance rests on a CSPRNG, low collision probability, and sound operational design.

### Testing across JDK/provider migrations

A system may change JDK versions, security providers, FIPS modes, or password-hashing libraries. Test verification against **historical records created on the old environment**, especially with Unicode passwords, rather than only testing create→verify on the new JVM. A complete record format is necessary, yet you must also keep password character-to-KDF-input conversion consistent.

## 15. Typical mistakes

1. **Storing only the hash without salt/iterations/algorithm.** When config changes, legacy records can no longer be reliably verified.
2. **Single-pass `SHA-256(password)` or `SHA-256(password+salt)`.** Lacks computational cost to resist offline guessing.
3. **Using one salt for every user.** Defeats the primary benefit of unique salts.
4. **Using timestamp, email, or `Random` to generate salts.** Lacks cryptographic randomness.
5. **Changing the current iteration count and verifying all old records with it.** Valid passwords fail to match.
6. **Bumping the `iterations` field in the DB without recomputing the verifier.** The record becomes unverifiable.
7. **Accepting cost parameters sent by the client.** Lets clients downgrade security or trigger CPU/RAM exhaustion.
8. **Omitting upper-bound checks on KDF params.** Corrupted or malicious records can cause denial of service.
9. **Storing the pepper right next to the hash and salt.** Loses its extra defense value if only the database leaks.
10. **Logging passwords, derived verifiers, or sensitive records.** Multiplies the places holding material usable for password guessing.
11. **Comparing hashes with prefixes, improper `equals`, or partial byte checks.** Weakens verification integrity.
12. **Changing normalization/encoding without versioning.** Users with valid passwords get locked out.
13. **Believing PBKDF2 256-bit output gives an 8-char password 256-bit entropy.** Entropy depends on password creation, not output length.
14. **Migrating to Argon2id by hashing the PBKDF2 hash.** Fails to create an Argon2id verifier of the original password, breaking security and migration.
15. **Rehashing before verification succeeds.** Risk of altering a user's record before proving the requester knows the password.
16. **Measuring single-verify latency without considering total concurrent load.** Overly heavy KDFs can bottleneck the service.
17. **Using a password hash as a bearer token.** Anyone obtaining the record could impersonate users on a misdesigned API; records are strictly for server-side verification.

## 16. Self-check questions

**Question 1.** Two users have the same password; why are their password records usually unequal?  
**Answer:** Each record gets its own random salt; the same password with different salts produces different verifiers. The salt must be stored with the record so verification knows which salt to use.

**Question 2.** After raising PBKDF2 from 200,000 to 600,000 rounds, can you verify all records using 600,000 rounds?  
**Answer:** No. Legacy records must be verified using their stored 200,000 rounds. Only once the password matches can you create a new record with 600,000 rounds and a fresh salt.

**Question 3.** Does `PBEKeySpec(password, salt, 600000, 256)` mean the program created a “256-bit password”?  
**Answer:** No. 256 is the **derivation output length in bits**, not a measure of password entropy. Weak passwords can still be guessed offline.

**Question 4.** A receiver sees a record claiming 1,000,000,000 iterations. Should it run `SecretKeyFactory` just to “check thoroughly”?  
**Answer:** No. Validate upper bounds before spending CPU, reject out-of-policy records, and alert operations appropriately.

**Question 5.** Does a salt need to be kept secret like a pepper?  
**Answer:** No. Salts are public and stored alongside the record. A pepper is an extra secret kept separate from the database if the architecture uses one.

**Question 6.** When switching from PBKDF2 to Argon2id, can you convert all records offline without knowing the original passwords?  
**Answer:** You cannot produce an equivalent Argon2id verifier of the password from a PBKDF2 verifier. You need the original password upon successful login or a reset flow.

**Question 7.** Does `MessageDigest.isEqual` make the entire login endpoint constant-time?  
**Answer:** No. It helps when comparing verifier bytes; lookup, parsing, KDF, rate limiting, and operational branches still have their own timing characteristics.

**Question 8.** Is a record stored in Base64url “encrypted” so it needs no read access control?  
**Answer:** No. Base64url is an encoding, not encryption. Stored verifiers still require strict access controls and backup protection.

**Question 9.** In Argon2id, what does `m=19456,t=2,p=1` mean?  
**Answer:** 19 MiB of memory, 2 passes, and 1 lane/degree of parallelism. These are algorithm parameters to store alongside the record, not salt/hash bytes.

**Question 10.** Could rehash-on-login overwrite a new password if the user just reset it in another request?  
**Answer:** Yes, if updated unconditionally. Use optimistic locking/compare-and-swap so the record is replaced only if the stored row is still the verified record.

## 17. Summary and references

A **proper password record** carries enough information to rerun verification: **format version, algorithm, work factor, salt, output length, verifier**, plus any metadata related to encoding/pepper. Create records with a fresh salt and current profile; verify with the **stored** parameters; rehash only after verification succeeds and update the DB atomically. Java 17 provides `PBKDF2WithHmacSHA256` for direct demonstration; Argon2id requires a suitable maintained library and must persist full `m`/`t`/`p` and version parameters.

Technical references for real-world design:

- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) — algorithms, salts, work factors, peppers, and hash upgrades.
- [RFC 9106 — Argon2 Memory-Hard Function](https://www.rfc-editor.org/rfc/rfc9106.html) — Argon2id, `m`/`t`/`p`, and parameter structure.
- [Java SE 21 — PBEKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html) — password `char[]`, salt, iterations, key length, `clearPassword`.
- [Java SE 21 — SecretKeyFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/SecretKeyFactory.html) — deriving/generating secrets via JCA.
- [Java SE 21 — SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html) — generating cryptographically random salts.
- [Java SE 21 — MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html) — comparing verifier bytes.