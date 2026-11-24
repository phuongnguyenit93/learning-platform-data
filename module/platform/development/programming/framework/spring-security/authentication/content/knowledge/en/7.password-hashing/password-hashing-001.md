# PasswordEncoder and the Difference Between Hashing and Reversible Encryption

In Spring Security, **`PasswordEncoder`** is the contract used to **transform a password into a stored value and verify whether a user-submitted password matches the stored value**. For a suitable password storage algorithm such as bcrypt, scrypt, PBKDF2, or Argon2id, this transformation is **one-way**: the application does not need — and should not have — a method to "decrypt a hash to recover the password".

**Reversible encryption** is a different matter: data is transformed into ciphertext using a key, and a party holding the valid key can decrypt it back into plaintext. Encryption is suitable for secrets that **truly need to be recovered** (such as credentials for connecting to an external system), but it is **not the default choice for storing user login passwords**.

This lesson belongs to the **Password Hashing** section of Spring Security Authentication. After this lesson, you will understand the `encode`, `matches`, and `upgradeEncoding` contracts; salt and work factor; the difference between hashing, encryption, and encoding; `BCryptPasswordEncoder` and `DelegatingPasswordEncoder`; registration/login integration; how to upgrade hashes; a runnable Java 17 example; testing; and common security pitfalls.

## 1. Three Concepts to Distinguish Immediately

| Mechanism | Can plaintext be recovered directly? | Goal | Example |
|---|---|---|---|
| **Encoding** (representation) | **Yes**, by decoding; no secret key needed | Change format for transmission/storage | Base64, URL encoding, hex |
| **Encryption** | **Yes**, when holding a valid decryption key | Protect content that needs to be reused | AES-GCM for an API secret that must be recovered |
| **Password hashing / KDF** | **No reverse decryption operation** | Verify a password without keeping the original | Argon2id, bcrypt, scrypt, PBKDF2 |

Subtle point: a hash is not an operation where "no one can deduce the password". An attacker who obtains the hash can still **guess many passwords**, use the same algorithm to check each candidate, and perform an **offline attack**. A good password hashing algorithm creates sufficiently high computational/resource cost to make trying large numbers of candidates more expensive. Therefore, you must not merely "use a hash", but also choose an appropriate algorithm, salt, and cost.

### 1.1. Why Is Base64 Not Security?

~~~text
Plaintext: password123
Base64   : cGFzc3dvcmQxMjM=
Decode   : password123
~~~

Base64 only changes the representation. Anyone with the Base64 string can immediately recover the plaintext without any secret. A `{base64}...` value or Base64 ciphertext does not prove safe password hashing.

### 1.2. Password Hashing Differs from Checksum Hashing

An application may compute `SHA-256` for a file to detect whether the file has changed. However, SHA-256 is designed to be **very fast**; using `SHA-256(password)` directly for password storage enables an attacker to test a huge number of candidate passwords rapidly.

Password hashing algorithms are designed to be **intentionally resource-intensive**. For example:

- **Argon2id:** memory-hard, with memory/time/parallelism parameters; recommended as the primary choice by OWASP when supported by the system.
- **scrypt:** memory-hard; an appropriate alternative option.
- **bcrypt:** widely used and directly supported by Spring Security; has a cost parameter and input length limitations to note.
- **PBKDF2:** performs many iterations, with configurations used for environments requiring compliance with relevant standards/FIPS.

Manually salted SHA-256 hashes such as `SHA256(salt || password)` still lack the brute-force slowdown of proper password KDFs. HMAC-SHA-256 or SHA-256 also does not become a good password-hashing scheme simply because you "hash many things together".

## 2. The PasswordEncoder Contract: encode, matches, upgradeEncoding

The `org.springframework.security.crypto.password.PasswordEncoder` interface is essentially:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);

    boolean matches(CharSequence rawPassword, String encodedPassword);

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

This is an **abbreviated framework signature**, not a standalone class you need to write yourself. Make sure you understand:

1. **`encode(rawPassword)`:** produces a storable value to verify the password later. With bcrypt and modern algorithms using random salts, two calls with the same password **usually produce two different hash strings**.
2. **`matches(rawPassword, encodedPassword)`:** uses the newly submitted password and the stored value to check whether they match. It **does not decrypt the hash** and does not require knowing the original password from the database.
3. **`upgradeEncoding(encodedPassword)`:** helps check whether an old hash should be regenerated according to the current configuration/algorithm. The interface's default method returns `false`; each encoder can override it.

### 2.1. Do Not Call encode Again and Compare with equals

**Wrong:**

~~~java
String newHash = encoder.encode(submittedPassword);
boolean ok = storedHash.equals(newHash);
~~~

**Right:**

~~~java
boolean ok = encoder.matches(submittedPassword, storedHash);
~~~

Both snippets are **illustrative only**, assuming the variables are already provided. With bcrypt, `encode` generates a random salt each time; comparing two newly generated hash strings with each other can fail **even when the password is completely correct**. `matches` reads the necessary salt/parameters from the encoded hash and performs verification according to the algorithm.

### 2.2. Standard Register and Login Flow

~~~text
REGISTRATION / PASSWORD CHANGE
Client new password --TLS--> Application
       |
       +--> Validate policy, protect logs, and enforce input limits
       +--> passwordEncoder.encode(rawPassword)
       +--> Store encodedPassword in password_hash in DB
       '--> Never store rawPassword in DB/session/logs

LOGIN
Client submitted password --TLS--> Authentication Filter
       |
       +--> DaoAuthenticationProvider
       |        +--> UserDetailsService loads UserDetails from DB
       |        +--> PasswordEncoder.matches(raw, storedHash)
       |        +--> Check account/credential status
       |        '--> Authentication succeeds or fails
       |
       '--> Filter/handler manages SecurityContext + session/token
~~~

`UserDetailsService` is responsible for **loading data**, not "decrypting passwords". In an application using `DaoAuthenticationProvider`, you must configure a `PasswordEncoder` policy compatible with the stored hash format, otherwise users may be rejected even when entering the right password.

**A password hash is not a login token**: knowing someone's hash must not allow sending the hash directly as a password over an API. Always distinguish between the raw password submitted by a user and the encoded hash residing in the data store. Never design an accidental "pass-the-hash" login method.

## 3. Salt, Cost, and Format of the Stored Hash

### 3.1. What Is Salt?

**Salt** is a random value used specifically for each individual hash. It ensures two accounts with the same password do not have identical hashes and thwarts precomputed tables (rainbow tables). Salt **does not need to be kept secret** and is usually encoded **inside the hash string itself** alongside the algorithm parameters.

An example of bcrypt format looks like:

~~~text
$2a$10$<22 salt characters in bcrypt format><remaining hash part>
       | 
       +-- cost = 10 (illustrative)
~~~

The string above is a structural diagram, **not a valid bcrypt hash for direct verification**. An actual hash has its prefix/cost/salt/checksum encoded per the algorithm specification. When generating with `BCryptPasswordEncoder`, you normally store the **entire `encode(...)` string** in the `password_hash` column, without manually splitting salt and hash, and never generating salt with `Math.random()`.

### 3.2. Why Do Hashes for the Same Password Differ?

~~~text
Password A = "same-password"
Password B = "same-password"

Hash A = bcrypt(password, randomSaltA, cost)
Hash B = bcrypt(password, randomSaltB, cost)

SaltA != SaltB (with very high probability)
=> Encoded hash strings differ even though plaintext is identical
~~~

Do not test randomness by asserting two hashes are unequal with `equals` in a mandatory test: random salt collision probability is tiny, yet logically not an impossibility. Verify with `matches` against each hash and verify that the library uses a CSPRNG.

### 3.3. What Is Work Factor?

Good password hashing deliberately incurs processing cost. BCrypt has a work factor called **cost**, which increases computational expense sharply as the parameter increases. The choice of cost must be benchmarked on production hardware, ensuring it is hard enough against offline cracking without causing login CPU bottlenecks or making the service vulnerable to denial of service.

Example:

~~~java
PasswordEncoder bcrypt = new BCryptPasswordEncoder(12);
~~~

This is an **illustrative configuration snippet**, not a standalone program. Cost 12 is not a universal optimal number. Measure `matches` latency under realistic concurrency and choose according to current security policy. An overly fast algorithm is vulnerable to offline attacks; an overly heavy configuration without rate limiting can expose the login endpoint to DoS.

### 3.4. Bcrypt's 72-Byte Limit

Many bcrypt implementations process at most the **first 72 input bytes**. Bytes do not equal character count: Unicode strings can use multiple UTF-8 bytes per character. If an application accepts longer passwords and the encoder truncates them, two passwords sharing the same prefix can be treated as identical beyond the limit.

Do not arbitrarily pre-hash `SHA-256(password)` before passing into bcrypt as a "trick" without understanding password shucking, null bytes, output encoding, and upgrade policies. Prefer algorithms/implementations supporting appropriate lengths, or enforce input limits and clearly explain the rules on the backend; ensure users' passwords are not silently truncated. When switching algorithms, verify compatibility with old hashes and library versions.

### 3.5. How Does Pepper Differ from Salt?

**Pepper** is a **shared system-wide or credential-group secret** kept **separate from the DB** (secret manager/HSM/KMS) to add defense-in-depth if only the DB is leaked. Salt is a public, per-hash value typically stored together with the hash.

| Factor | Salt | Pepper |
|---|---|---|
| Needs to be secret? | No | **Yes** |
| Per user/hash? | Usually unique per hash | Usually system-level or versioned secret |
| Where stored | Inside the encoded hash | Secret manager/HSM or other secret management mechanism |
| If value is lost | Hash usually cannot be verified if salt is missing from format | Must have recovery/rotation policy; may force user resets |
| Can it replace a strong password KDF? | No | No |

If adding pepper, you must design a clear cryptographic construction (such as HMAC over an appropriate output, mindful of secret source), versioning, rotation, and login verification. Do not invent an ad-hoc "append pepper to password" formula and assume it is secure; prefer approaches vetted by documentation/security teams.

## 4. BCryptPasswordEncoder and DelegatingPasswordEncoder

Spring Security provides `BCryptPasswordEncoder` out of the box, allowing verification of bcrypt hashes and adjustment of the work factor.

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder(10);

String hash = encoder.encode("example-password");
boolean ok = encoder.matches("example-password", hash);
~~~

This is an illustrative Java snippet; it requires imports for `PasswordEncoder` and `BCryptPasswordEncoder`. In a registration flow, the hash is stored in the DB; at login, the backend fetches the corresponding account's hash and calls `matches`. The hash includes the salt, so there is no need to create a separate `salt` column for standard bcrypt format.

### 4.1. Why Do We Need DelegatingPasswordEncoder?

Long-lived projects may store passwords using multiple different algorithms, for example:

~~~text
{bcrypt}$2a$10$...  -> bcrypt encoder
{pbkdf2}...         -> encoder corresponding to ID pbkdf2
{scrypt}...         -> scrypt encoder
{argon2}...         -> Argon2 encoder
~~~

These are **format-illustrative strings**, not actual hashes used for login. `DelegatingPasswordEncoder` stores values in the format:

~~~text
{id}encodedPassword
~~~

- `id` identifies the encoder responsible for `matches`.
- `encodedPassword` is that algorithm's data; it may contain salt and cost.
- The `idForEncode` configuration determines the algorithm for **new passwords**.
- During `matches`, the encoder selects the algorithm according to `{id}` in the stored data.

Spring Security provides a common factory:

~~~java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

With the typical default mapping, new passwords are encoded with bcrypt and receive the `{bcrypt}` prefix. This increases flexibility for future algorithm transitions without immediately breaking all old hashes.

**Note:** The default mapping may support weak/legacy encoders, including the `{noop}` ID for compatibility/migration purposes. The fact that an encoder **can read** a format does not mean it is permitted for **creating new hashes** in production. New registration flows must use an approved strong encoder.

### 4.2. Error "There is no PasswordEncoder mapped for id null"

If the DB contains raw bcrypt hashes, e.g., starting with `$2a$...`, while the application configures `DelegatingPasswordEncoder` expecting `{id}...`, calling `matches` can throw `IllegalArgumentException` because no ID can be determined (null). It can also happen if an ID is used that is absent from the mapping.

Do not "quick fix" this with `NoOpPasswordEncoder` or by treating every ID-less hash as plaintext. Once you have **reliably verified** that all those legacy rows are valid bcrypt, a migration can prepend the `{bcrypt}` prefix to the string **without recomputing the hash**:

~~~text
Before: $2a$10$...stored bcrypt...
After : {bcrypt}$2a$10$...stored bcrypt...
~~~

This is a simplified representation, not an executable SQL migration. In production, inventory formats row by row, back up data, test `matches` with known test credentials, and use an idempotent migration; do not repeatedly prepend the prefix across multiple runs.

### 4.3. Can a Fallback Encoder Be Used?

`DelegatingPasswordEncoder` allows configuring `setDefaultPasswordEncoderForMatches(...)` to handle hashes missing an ID. However, the chosen fallback must strictly match a **known legacy format**, without opening the door for `{noop}` or raw passwords to be accepted as valid hashes. Prefer explicit ID formats, planned migrations, and cross-version testing before and after rollout.

Changing algorithms requires distinguishing:

- **Reading old hashes:** use a compatible encoder according to the stored ID.
- **Writing new hashes:** use the currently approved algorithm/work factor.
- **Upgrading hashes:** only after verifying the correct raw password in a secure flow do you have the information needed to create a new hash.

## 5. Runnable Java 17 Example: One-Way Hashing and Reversible Encryption

This example intentionally places the two techniques side by side:

1. **Spring Security BCrypt/DelegatingPasswordEncoder:** generates and verifies hashes, **with no password decryption operation**.
2. **Java Cryptography API with AES-GCM:** encrypts a sample string, then uses a **valid key** to decrypt it back to plaintext. This illustrates secrets that must be recovered, **not a recommendation to use AES-GCM for storing login passwords**.

To keep stdout deterministic, the program **does not print ciphertexts, salts, or raw bcrypt hashes** (which are randomized). It only prints booleans and configuration-determined states.

### 5.1. Project Structure

~~~text
password-encoder-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/PasswordEncoderDemo.java
~~~

Create `settings.gradle`:

~~~groovy
rootProject.name = 'password-encoder-demo'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-crypto:6.3.8'
    implementation 'org.springframework.security:spring-security-core:6.3.8'
}

application {
    mainClass = 'example.PasswordEncoderDemo'
}
~~~

The demo only requires Java 17, Spring Security Core/Crypto, and Gradle; no Spring Boot, Servlet, JPA, or database is needed. In a real Spring Boot application, the Spring Security version is typically managed by a BOM rather than pinned directly like in this console example.

### 5.2. Complete Java Program

Create `src/main/java/example/PasswordEncoderDemo.java`:

~~~java
package example;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordEncoderDemo {

    public static void main(String[] args) throws Exception {
        String rawPassword = "Study!Password#2026";

        // Password hashing: one-way, with bcrypt's salt and cost.
        PasswordEncoder bcrypt = new BCryptPasswordEncoder(10);
        String storedHash = bcrypt.encode(rawPassword);

        System.out.println("bcrypt format -> "
                + storedHash.startsWith("$2"));
        System.out.println("bcrypt correct -> "
                + bcrypt.matches(rawPassword, storedHash));
        System.out.println("bcrypt wrong -> "
                + bcrypt.matches("wrong-password", storedHash));

        // Delegating encoder includes an ID to select the algorithm during verification.
        PasswordEncoder delegating =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();
        String tagged = delegating.encode(rawPassword);

        System.out.println("delegating prefix -> "
                + tagged.startsWith("{bcrypt}"));
        System.out.println("delegating correct -> "
                + delegating.matches(rawPassword, tagged));
        System.out.println("legacy bcrypt with id -> "
                + delegating.matches(rawPassword, "{bcrypt}" + storedHash));

        // A cost=10 hash is considered in need of upgrade under a cost=12 policy.
        BCryptPasswordEncoder strongerBcrypt =
                new BCryptPasswordEncoder(12);
        System.out.println("bcrypt needs upgrade -> "
                + strongerBcrypt.upgradeEncoding(storedHash));

        // Reversible encryption: example of a secret that must be read back; DO NOT
        // use instead of password hashing for storing login passwords.
        String serviceSecret = "demo-external-service-secret";
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        GCMParameterSpec params = new GCMParameterSpec(128, nonce);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, key, params);
        byte[] ciphertext = encrypt.doFinal(
                serviceSecret.getBytes(StandardCharsets.UTF_8));

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, key, params);
        byte[] restoredBytes = decrypt.doFinal(ciphertext);
        String restored = new String(
                restoredBytes, StandardCharsets.UTF_8);

        System.out.println("AES-GCM decryptable -> "
                + serviceSecret.equals(restored));
    }
}
~~~

### 5.3. Running and stdout

If the Gradle Wrapper exists in the project directory, run:

~~~bash
./gradlew run
~~~

If there is no wrapper yet but a compatible Gradle is installed, use `gradle run`. In Windows PowerShell with the wrapper, use `.\gradlew.bat run`.

Output of the **`System.out.println` statements** in the program (excluding Gradle logs):

~~~text
bcrypt format -> true
bcrypt correct -> true
bcrypt wrong -> false
delegating prefix -> true
delegating correct -> true
legacy bcrypt with id -> true
bcrypt needs upgrade -> true
AES-GCM decryptable -> true
~~~

Why are these lines true?

- `BCryptPasswordEncoder(10)` produces a bcrypt hash starting with `$2...`; `matches` is true for the original raw password and false for another password.
- Spring Security 6.3's `createDelegatingPasswordEncoder()` factory uses bcrypt for new encodings and adds the `{bcrypt}` prefix; `matches` reads the prefix to pick the right encoder.
- Concatenating `"{bcrypt}" + storedHash` simulates **attaching an ID to a legacy bcrypt hash of known format**, enabling the delegating encoder to verify with the corresponding algorithm.
- `BCryptPasswordEncoder(12).upgradeEncoding(storedHash)` reports that an upgrade is needed when the old hash has cost 10, lower than 12.
- AES-GCM **can be decrypted** because the program still has the `key`, `nonce`, and ciphertext; bcrypt has no equivalent `decrypt` method.

**Limitations of the AES-GCM example:** the key and nonce are generated in RAM to demonstrate the roundtrip. Real systems must manage keys via KMS/HSM/secret manager; ensure **never to reuse a nonce with the same GCM key**, store the nonce alongside the ciphertext in a versioned format, consider AAD, and rotate keys. If the key is lost, ciphertext may be unrecoverable; if the key is leaked, attackers can decrypt it. **Never write keys into source code or the same database table without a protection strategy.**

### 5.4. Why Is This Not "Decrypting a Hash"?

`PasswordEncoder.matches(...)` checks a candidate password against the stored hash. It **does not** recover the original plaintext. On the other hand, `Cipher.DECRYPT_MODE` requires a valid key and the necessary nonce/metadata; it returns plaintext if ciphertext authentication succeeds. The two APIs solve **two completely different needs**.

With password hashing, even though the hash cannot be decrypted back, someone possessing the hash can still guess common passwords and test them offline. That is why slow KDFs, reset controls, rate limiting, and passwords with reasonable entropy are required.

## 6. Integrating with Spring Security Authentication

### 6.1. PasswordEncoder Bean Used for Registration and Login

An illustrative Spring Boot configuration:

~~~java
@Configuration
class SecurityBeans {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
~~~

The snippet above **is not a standalone project**; it requires the `spring-boot-starter-security` dependency, imports, and application configuration. The encoder bean should be used consistently for new passwords and by the provider verifying login. Do not create an arbitrary policy/encoder per request without hash version management.

### 6.2. Registration: Store Only the encode Result

~~~java
public UUID register(String username, String rawPassword) {
    validatePasswordPolicy(rawPassword);

    String hash = passwordEncoder.encode(rawPassword);
    Account account = new Account(
            UUID.randomUUID(), username, hash);

    return accountRepository.save(account).getId();
}
~~~

This is an **illustrative integration snippet**; `validatePasswordPolicy`, `Account`, `accountRepository`, and the bean must exist, and it does not yet include transactions, unique constraints, or email verification. Input limits, rate limiting protection, and password policies are the application's responsibility.

In the database, store the password hash in a column long enough for formats with IDs and future parameters (e.g., `TEXT`); do not use a column too short that causes encoded hashes to be truncated. A hash is not data to display to the client: response DTOs must exclude the password hash.

### 6.3. Login: Provider Compares Against Stored Hash

~~~java
@Bean
AuthenticationProvider usernamePasswordProvider(
        UserDetailsService users,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider();
    provider.setUserDetailsService(users);
    provider.setPasswordEncoder(passwordEncoder);
    return provider;
}
~~~

This is a configuration snippet for Spring Security 6.3.x and **does not compile standalone** without imports, annotations, and dependencies. In newer Spring Security versions, the provider initialization API may change or recommend a constructor accepting `UserDetailsService`; always check the JavaDoc for your exact application version.

`UserDetailsService` loads `UserDetails` containing the **encoded password** and account status. `DaoAuthenticationProvider` invokes the encoder to compare the raw password from the request with the hash; if successful, the provider returns a trusted `Authentication` and the filter manages `SecurityContext`. Never return an authenticated `Authentication` solely because the username exists.

### 6.4. Lost Passwords Must Be Reset, Not Decrypted

Because password hashes cannot be decrypted directly, support users who forget their password via a **password reset flow**, never by sending back the old password:

1. Accept the request and return a public message that does not reveal whether the account exists.
2. Verify ownership through an appropriate channel/process, issuing a high-entropy, short-lived, single-use reset token.
3. Store the reset token securely (typically stored as a hash or verifiable data), apply rate limiting, and record appropriate audit logs.
4. After verifying the token, accept a new password compliant with policy and call `passwordEncoder.encode(newPassword)`.
5. Update the new hash within a transaction and follow your policy for revoking sessions/refresh tokens or sending security notifications.
6. Never store/send the new password in logs/emails, and never use a long-lived reset token as an API access token.

**If someone asks to "decrypt a user's password to send in a support email", that is a sign of a broken password storage design.**

## 7. Upgrading Hashes When Policy Changes

A work factor suitable last year may become too light on newer hardware. Many systems also migrate from legacy hashes to Argon2id or increase bcrypt cost. Because hashing is one-way, **a new algorithm's hash cannot be generated from an old hash while still verifying the same password**, except via special pre-designed mechanisms. Normally you must have the **raw password just entered correctly by the user**, or ask them to reset.

### 7.1. Meaning of upgradeEncoding

~~~java
if (encoder.matches(rawPassword, storedHash)
        && encoder.upgradeEncoding(storedHash)) {
    String strongerHash = encoder.encode(rawPassword);
    // Save strongerHash within a transaction and according to security policy.
}
~~~

This is **illustrative logic**, not a standalone runnable service. `upgradeEncoding` is only a signal to consider re-encoding; it does not write to the database itself. With `DelegatingPasswordEncoder`, the signal may relate to an old format ID; with `BCryptPasswordEncoder`, it may relate to a low cost. Always use the newly approved encoder when creating the new hash.

### 7.2. Things to Guarantee When Rehashing

- Only rehash **after successful verification of the raw password**; do not trust an unverified raw password.
- Do not treat the old hash as a "raw password" to rehash: `encode(storedHash)` does not allow the user to log in with their original password.
- When multiple concurrent logins occur or the user resets their password, use optimistic locking/CAS on version or the old hash. Prevent a stale rehash request from overwriting a newly changed password.
- Update the hash inside a transaction and handle cache/sessions per policy; do not fail the user's login merely because the upgrade step did not complete, while logging operational errors appropriately.
- When switching to another algorithm, ensure older nodes can still read the new hashes during a rolling deployment, or deploy in a compatible order.
- Accounts that have not logged in for a long time may remain un-rehashed. You can set a policy requiring a reset upon return or when a hash becomes too old.

### 7.3. Do Not Mislabel Formats

If a row is unsalted SHA-256, adding the `{bcrypt}` prefix **does not turn it into bcrypt**. If a row is already `{bcrypt}$2a$...`, prepending `{bcrypt}` again also corrupts the format. Migrations must classify based on actual stored data, build test cases for each format, and include rollback and metrics.

### 7.4. Example Policy on a Long-Lived System

~~~text
Initial database:
  account A: {bcrypt}... (cost 10)
  account B: {bcrypt}... (cost 12)
  account C: {legacy}... (inventoried legacy algorithm)

New policy:
  New password -> newly approved encoder
  Login A      -> matches true -> upgrade detected -> safely rehash
  Login B      -> can remain unchanged if policy is satisfied
  Login C      -> verify with controlled legacy adapter -> rehash
  No login     -> await reset/upgrade per policy
~~~

Do not let an unknown `legacy` decoder or `NoOpPasswordEncoder` act as an open fallback for any unprefixed string. If data was ever stored in plaintext, that is a severe risk requiring dedicated handling, including incident evaluation and forced resets where appropriate.

## 8. Password Hashing Still Needs Multiple Layers of Defense

**Strong hashing does not replace other defensive measures.**

| Risk | Complementary Measure |
|---|---|
| Password eavesdropping in transit | TLS/HTTPS, proper proxy/header/cookie configuration |
| Password logged or sent in URL | Do not log request bodies/Authorization headers containing secrets; use form/body over HTTPS |
| User chooses weak/reused password | Length policy, blocklist of common/breached passwords, MFA |
| Online brute force/password spraying | Rate limiting, anomaly monitoring, reasonable lockout/risk-based throttling |
| Database hash leak | Adaptive KDF, unique salt, appropriate cost, properly implemented optional pepper |
| Attacker exhausting login CPU | Request/body and concurrency limits, cost benchmarking, rate limiting |
| Hash returned via API | DTO omitting `passwordHash` field, least-privilege DB access, audit and redaction |
| Replacing hash with client-supplied data | Validate reset flow, never allow clients to submit hashes as valid credentials |
| Cached `UserDetails` mutated after login | Separate cache objects from authentication principal, manage `eraseCredentialsAfterAuthentication` |
| Session/JWT remains valid after password change | Session/token revocation, rotation, authentication versioning as required |

### 8.1. Does Salt Make a Hash Completely Safe?

No. Salt reduces the advantage of precomputed hash tables and ensures hashes differ across accounts; it **does not increase the entropy** of the user's password. Overly common passwords can still be guessed via offline brute force. A slow KDF only increases the cost per guess. Therefore, strong passwords, MFA, breached-password detection policies, and defense in depth remain essential.

### 8.2. Why Is Encrypting Passwords with AES-GCM Not Enough?

If an application encrypts passwords with AES-GCM and keeps the decryption key in the same environment needed for login, an attacker who obtains both the database and the key (or compromises the service) can **recover the plaintext of all passwords**. Passwords are secrets that the server only needs to **verify**, without needing to know the original again after registration. One-way hashing avoids such a bulk recovery point, though it does not completely eliminate offline guessing.

AES-GCM remains very useful when a value **needs to be recovered** (for instance, a provider token that the server must send to an external API), with proper key management and access control. Never turn a password authentication requirement into a decryptable requirement just because "AES is strong".

### 8.3. Should We Use Argon2id or bcrypt?

OWASP currently recommends preferring Argon2id for password storage when supported by the environment, scrypt when another memory-hard choice is needed, bcrypt when legacy systems/appropriate conditions apply, and PBKDF2 for relevant compliance scenarios. Spring Security provides corresponding encoders, though some implementations like Argon2 may require extra crypto dependencies and have version-specific parameters.

Do not blindly switch the entire application to a new algorithm in a single deploy if old data or nodes cannot read it yet. Evaluate threat model, operational capacity (CPU/RAM), compliance standards, migration roadmap, and benchmarks on realistic workloads. Exact numeric work factor details should be checked against the latest OWASP guidance at implementation time.

### 8.4. Credential Erasure After Login

`ProviderManager` typically erases credentials on the resulting `Authentication` by default if the object implements `CredentialsContainer`. This does not lose the password hash properly stored in the database, but it **can mutate a mutable `UserDetails` shared with a cache** if the authentication principal points to that exact instance.

Do not arbitrarily disable credential erasure just to "keep the hash in cache". Prefer separating per-request/principal objects without secrets, and test logins across cache hits and concurrency.

## 9. Typical Implementation Mistakes

**Mistake 1 — "If you can encode, you must be able to decode".**  
`PasswordEncoder` does not support decrypting hashes; use `matches`. If you need to retrieve plaintext to display it, the password storage design is already wrong.

**Mistake 2 — Using `Base64.getEncoder()` as a password hashing solution.**  
Base64 uses no key and can be decoded directly. You must use an appropriate password KDF.

**Mistake 3 — Using `MessageDigest SHA-256` directly for passwords.**  
SHA-256 is too fast to resist offline guessing. Use Argon2id/scrypt/bcrypt/PBKDF2 per security policy.

**Mistake 4 — Re-encoding the raw password and calling `equals` against the old hash.**  
Adaptive hashes use random salts; use `matches(raw, stored)`.

**Mistake 5 — Using `NoOpPasswordEncoder` in production.**  
It does not hash or protect passwords. It may only appear in controlled migration/test scenarios, never as the default for registration/login.

**Mistake 6 — Configuring DelegatingPasswordEncoder when DB stores hashes missing `{id}`.**  
This can trigger an unmapped id/null error. Inventory legacy formats, add the proper prefix or a suitable migration adapter; never treat every unprefixed string as plaintext.

**Mistake 7 — Setting cost as high as possible without measuring.**  
Excessive cost can saturate CPU and create a DoS target. Benchmark under concurrency and apply rate limiting.

**Mistake 8 — Not enforcing bcrypt's input byte limit.**  
The 72-byte limit in many implementations can cause password truncation. Validate inputs by byte length/policy and test Unicode.

**Mistake 9 — Generating a salt once and reusing it for all accounts.**  
This loses the benefit of unique salts. Use a vetted implementation that generates a unique salt inside `encode`.

**Mistake 10 — Automatically converting old hashes using `encode(storedHash)`.**  
That is not a valid password migration; you must verify the raw password first and then generate the new hash.

**Mistake 11 — Hardcoding pepper or AES keys in the repository.**  
Even with a strong secret key, a code/config leak can break protection. Use a secret manager/HSM, access controls, and a rotation policy.

**Mistake 12 — Printing hashes and raw passwords in logs/tests.**  
Hashes are also sensitive credential material. Only log safe events and identifiers sufficient for investigation.

**Mistake 13 — Using unauthenticated AES ECB/CBC to store decryptable secrets.**  
If you truly must encrypt a secret, choose authenticated encryption such as AES-GCM with proper nonce/key management, and do not invent ad-hoc crypto protocols.

**Mistake 14 — Assuming password hashing also secures sessions.**  
After login you must still manage cookies, CSRF, session fixation, JWT/access tokens, and revocation. `PasswordEncoder` does not handle those responsibilities.

## 10. Test Scenarios

| Case | What Must Be Proven |
|---|---|
| `encode(raw)` then `matches(raw, hash)` | `true` for correct password |
| `matches(wrong, hash)` | `false` |
| Two `bcrypt.encode` calls for same raw password | Both hashes verify; salt is generated uniquely per the algorithm |
| Bcrypt hash with some characters altered | Must not authenticate successfully; format errors must be handled safely |
| DelegatingPasswordEncoder generates a new hash | Has `{id}` prefix matching policy |
| DelegatingPasswordEncoder reads a legacy hash with valid ID attached | Selects the corresponding encoder |
| Hash missing ID or with unknown ID | Does not fall back to plaintext; errors are handled/logged in a controlled manner |
| Old cost lower than new policy | `upgradeEncoding` via appropriate encoder signals upgrade needed |
| After rehashing with verified raw password | Subsequent logins with the old password match the new hash |
| Concurrent password reset and rehash | Old rehash must not overwrite the newly reset password |
| Unicode/long password | Complies with byte limit/normalization and encoder policy |
| Registering same password for multiple accounts | No global salt used; hashes are stored safely |
| Simulated database dump | No plaintext passwords, encryption keys, or pepper in DB |
| AES-GCM encrypt/decrypt | Decryption succeeds only with valid key/nonce/ciphertext |
| AES-GCM with modified ciphertext/tag | Decryption fails due to data authentication |
| Login rate limiting | Cannot send unlimited guesses to exhaust CPU |
| Spring DaoAuthenticationProvider | Uses the configured PasswordEncoder against UserDetails.password hash |
| After login, Authentication credentials | Raw password does not linger in context when using erasure-capable tokens |
| Reset password | Updates new encoded hash only after reset token verification |
| Switching algorithms during rolling deploy | Old/new nodes read required supported formats without disruption |

### 10.1. Quick Self-Check

**Question 1.** If you only have a bcrypt hash in the database, can you decrypt it to send back the password?  
**Answer:** No. You can verify a candidate password with `matches`; if the user forgot it, a reset is required.

**Question 2.** Why do two users with the same password usually have different bcrypt hashes?  
**Answer:** A unique random salt per `encode` call; the same password with different salts yields different encoded hashes.

**Question 3.** Why can `encode(password).equals(storedHash)` be false when the password is correct?  
**Answer:** The new `encode` call uses a new salt. Use `matches(raw, storedHash)`.

**Question 4.** When should AES-GCM be used instead of PasswordEncoder?  
**Answer:** When a secret genuinely needs to be decrypted and recovered for reuse, with proper key/nonce protection; not for storing login passwords.

**Question 5.** Is `{bcrypt}` in `DelegatingPasswordEncoder` a password or a salt?  
**Answer:** No. It is an identifier that selects the encoder to verify the encoded hash portion that follows.

**Question 6.** Should a shared pepper be stored in the same `accounts` table?  
**Answer:** No. Pepper is a secret that must be separated from the database and have key management/rotation.

**Question 7.** Can you rehash all users from old hashes to Argon2id without asking for their passwords?  
**Answer:** Not in a standard flow. You need the raw password verified during a new login or require a reset.

**Question 8.** Does good hashing make a system secure if the login API has no rate limiting?  
**Answer:** No. Hashing mainly protects against DB leaks and increases offline guessing cost; online guessing/credential stuffing still requires defenses.

## 11. Pre-Deployment Checklist

- [ ] Only store encoded passwords using an approved password KDF; never store plaintext, Base64, or reversible encryption.
- [ ] Choose Argon2id/scrypt/bcrypt/PBKDF2 based on policy, compliance, and CPU/RAM benchmarks.
- [ ] Use per-password random salts from a standard library; never share salts or roll custom KDFs from fast hashes.
- [ ] Distinguish `encode` during registration and `matches` during login; never compare by re-encoding.
- [ ] Store the full encoded format and algorithm ID (when using delegating), ensuring the column is long enough.
- [ ] Enforce input limits, protect against Unicode/byte limits, and avoid password policies that unintentionally lose entropy.
- [ ] Have a hash upgrade plan: `upgradeEncoding`, verified raw password, optimistic locking, and rolling migration.
- [ ] Never design an API to "retrieve the old password"; use a secure, single-use, expiring reset token.
- [ ] Never expose secrets in responses, logs, metrics, source code, or public config.
- [ ] Use TLS, rate limiting, appropriate anti-automation, and MFA when needed.
- [ ] If recoverable secrets must be encrypted, use separate authenticated encryption/key management; do not confuse with password hashing.
- [ ] Include unit/integration tests with real encoders/providers, hash formats, legacy data, and concurrent password changes.
- [ ] Never confuse password hashes with JWT/session/authorization; control each lifecycle independently.

**Remember:** `PasswordEncoder` is used to **verify whether a newly submitted password matches a stored hash**, **not to decrypt hashes**. For login passwords, **one-way adaptive hashing + salt + appropriate cost** is the foundation; for secrets that need recovery, **authenticated encryption and key management** are a separate problem.

### References

- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): one-way password transformation, `DelegatingPasswordEncoder`, `{id}encodedPassword` format.
- [Spring Security — PasswordEncoder JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html): `encode`, `matches`, `upgradeEncoding`.
- [Spring Security — BCryptPasswordEncoder JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html): salt, strength, and upgrade.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): username/password authentication using `UserDetailsService` and `PasswordEncoder`.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): algorithms, salt, work factor, bcrypt limits, pepper, and password hash upgrades.
- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): authenticated encryption and `AES/GCM/NoPadding`.
