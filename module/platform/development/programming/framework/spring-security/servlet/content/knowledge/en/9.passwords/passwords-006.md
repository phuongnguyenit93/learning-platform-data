# Salt, Pepper, and Managing Server-Side Secrets in Spring Security

## 1. Problem: storing passwords safely is more than calling a hash function

In a **Spring Boot / Spring Security Servlet** application, user passwords are highly sensitive authentication data. The system **must not store passwords in plaintext** and must not use a fast hash function like plain SHA-256 to store passwords. Instead, use a **computationally expensive password hashing/KDF algorithm** with random salts, paired with proper operations, secret management, and authentication policies.

Two concepts often mentioned together are:

- **Salt**: a random value **unique to each hash generation**, which does not need to be secret. Salt prevents two users with the same password from having identical password hashes and makes precomputed tables (rainbow tables) ineffective.
- **Pepper**: an **additional server-managed secret**, shared within a specific scope/key version by design and **never stored alongside password hash data**. Pepper can increase resistance **when only the database is compromised**, but adds operational responsibilities for protection, lifecycle, and key rotation.

**Key message:** salt is a normal and essential part of password hashing; pepper is an **optional, supplementary defense**, not a replacement for salt, slow hashing algorithms, multi-factor authentication, throttling, or application security. If an attacker compromises both the DB and the pepper secret on the server, the added benefit of pepper diminishes significantly.

This lesson belongs to the **Passwords** section and focuses on server-side password security verified in Spring Security on the Servlet stack. Examples use Java 17+, Spring Security Crypto/`PasswordEncoder`, and simulated hash storage; they are not a complete user management system.

## 2. Password hashing is not decryptable encryption

Three operations serve very different purposes:

| Technique | Has a secret key? | Reversible to recover original value? | Application to passwords |
| --- | --- | --- | --- |
| **Encryption** | Usually yes | Yes, if holding the key | Suitable for data that must be decrypted, **not how normal login passwords are stored** |
| **Fast hash** like SHA-256 | No | Not directly, but trivial to test candidate passwords at high speed | **Never use standalone** to store passwords |
| **Password hashing/KDF** like Argon2id, scrypt, BCrypt, PBKDF2 | Algorithm itself does not require a pepper | Cannot decrypt; verifies by recomputing and comparing | The right approach with suitable cost/salt parameters |

User passwords typically have lower entropy than random keys. An attacker who obtains a hash can test many candidate password strings via **offline guessing**. Thus, attack resistance depends on the **cost per guess** of the algorithm and password policy, not just the hash function's output length.

With Spring Security, the `PasswordEncoder` API lets you store hashes via `encode(rawPassword)` and verify via `matches(rawPassword, storedHash)`. Typically `BCryptPasswordEncoder` is used, or other adaptive algorithms/encoders suited to the version, libraries, and operational requirements.

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);

String storedHash = encoder.encode(rawPassword);
boolean valid = encoder.matches(loginPassword, storedHash);
~~~

This is an illustrative snippet; it requires importing `org.springframework.security.crypto.password.PasswordEncoder` and `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder` and declaring the password variables. `12` is BCrypt's cost factor, not salt length or a universal default for every environment. In production, benchmark on real hardware and factor in login load and DoS limits; a runnable example is in section 7.

## 3. Salt: public, random, unique per hash

### 3.1. What problem does salt solve?

Suppose two accounts both choose the password `correct-horse-example`:

~~~text
No salt (naive hashing model, must not be used):
  alice  -> HASH("correct-horse-example") -> same value
  bob    -> HASH("correct-horse-example") -> same value

With unique random salt and slow KDF:
  alice  -> KDF(password, salt_A, cost) -> hash_A
  bob    -> KDF(password, salt_B, cost) -> hash_B

  salt_A differs from salt_B  => hash_A differs from hash_B (with very high probability)
~~~

Salt also prevents one fixed precomputed table from matching millions of hashes under an overly simple hash scheme. Salt **does not turn a weak password into a strong one**: if the database leaks, attackers can still run dictionary guesses against **each individual hash** using the public algorithm and salt.

### 3.2. Is salt a secret?

**No.** Salt is normally stored **alongside the password hash** or encoded within the algorithm's output string. Security does not rely on hiding the salt; its value is randomly drawn, sufficiently strong, and distinct across hashes.

When using `BCryptPasswordEncoder`, the library generates a salt per `encode` call from an appropriate random source and stores version/cost/salt/derived hash inside the BCrypt string. A string typically looks like:

~~~text
$2a$12$<salt-encoded><hash-encoded>
~~~

The line above is a **syntax model**, not a hash usable for login. Prefixes like `$2a$`/`$2b$` and storage details vary by implementation. Do not slice the string at arbitrary positions to guess parameters when the library provides APIs.

Because the salt is already inside the BCrypt encoded string, verification only needs:

~~~java
boolean ok = encoder.matches(rawPassword, storedHash);
~~~

You **do not need** to fetch a salt from the DB and concatenate `salt + password` before calling `BCryptPasswordEncoder.encode`, nor do you need a separate salt column for BCrypt to work. If using another API, check that API's format/parameters; do not apply BCrypt conventions blindly to every KDF.

### 3.3. Why does the same password produce different hashes?

Example:

~~~java
PasswordEncoder bcrypt = new BCryptPasswordEncoder(10);
String hash1 = bcrypt.encode("same-password");
String hash2 = bcrypt.encode("same-password");

System.out.println(hash1.equals(hash2));  // typically false
System.out.println(bcrypt.matches("same-password", hash1)); // true
System.out.println(bcrypt.matches("same-password", hash2)); // true
~~~

This is an illustrative snippet. Expected output is `false`, `true`, `true`, because BCrypt generates a new random salt on each encode. Probabilistically, two random salts still have a vanishingly small chance of colliding, so the accurate phrasing is that **the two hashes will differ with very high probability**.

### 3.4. Never use predictable salts

Do not use username, email, timestamp, user ID, or a fixed constant as a substitute for a strong random salt. Those values can be guessed, duplicated, or changed, undermining the purpose of salting.

With BCrypt in Spring Security, the safest and simplest approach is **letting the encoder generate salts internally** instead of reimplementing this mechanism.

## 4. Pepper: a private server-side secret

### 4.1. How does pepper differ from salt?

Pepper is an application/system-level secret fed into creating and verifying password hashes. Pepper is only beneficial when an attacker obtains password data from the DB yet **does not obtain the pepper**.

| Criterion | Salt | Pepper |
| --- | --- | --- |
| Nature | Random value, not secret | High-entropy secret |
| Typical scope | Unique per hash generation | Can be shared across many records under a `keyId`/version |
| Storage | Storing with the hash in the DB is normal | **Separated from password DB**; placed in secret manager/KMS/HSM or proper protected store |
| Needed to verify? | Yes; usually embedded in the hash | Yes, if the design requires a pepper |
| When DB leaks | Attacker still has the salt | Attacker lacking pepper faces an extra barrier during offline cracking |
| When secret leaks | "Salt leak" is not meaningful | Requires incident assessment, key rotation, and reset/migration policy |
| Change/rotation | New hashes automatically get new salts | Harder; usually needs original password at user login or a reset flow |
| Necessity | Fundamental component of password hashing | Supplementary defense depending on threat model |

**Pepper is not a user's second password** and not an extra secret sent from the browser. It is a secret processed **on the server**, never sent to clients, and never stored in source code, Git, logs, responses, database backups, or debug tables.

### 4.2. What can and cannot pepper defend against?

Suppose only the `users(id, username, password_hash, pepper_id)` table is copied. The attacker has the BCrypt salt/cost/hash, but lacks the secret used in password preprocessing. If the pepper is strong enough and combined properly with the password, the attacker cannot test candidate passwords from the DB alone as easily as without a pepper.

However, pepper **helps little** in these cases:

- The attacker steals both the DB **and** the pepper from the server or secret manager.
- The attacker controls runtime execution and can invoke the auth service or observe passwords before hashing.
- SQL injection or authorization flaws allow direct access to business data; pepper does not patch those bugs.
- Passwords are stolen via phishing, malware, credential stuffing from another service, or session/token theft.
- Password verification calls lack rate limiting and are abused as an online guessing oracle; pepper does not replace throttling/MFA/monitoring.

Pepper is **defense in depth**, not a guarantee that "a database leak means passwords can never be cracked". Protection depends on implementation, keeping the secret safe, and the attacker's privileges.

### 4.3. Do not arbitrarily concatenate pepper to the start/end of a password

A design like:

~~~java
// Anti-pattern only; do not copy to production.
String combined = password + pepperString;
String stored = bcrypt.encode(combined);
~~~

can fail due to input encoding/length issues, encourages handling pepper as a `String`, complicates key management, and notably hits the input limit of some BCrypt implementations. Traditional BCrypt has an **effective ~72-byte input limit**; appending a pepper after a long password can prevent the pepper from contributing as expected.

For a clean structure, one approach is **keyed HMAC-SHA-256 before BCrypt**, then encoding the HMAC output to ASCII Base64URL (43 characters for 32 bytes, unpadded). HMAC folds the entire password into a fixed-length input, avoiding ambiguous concatenation and staying well under 72 bytes when passing the ASCII output into BCrypt.

This is **an architectural trade-off**, not a mandatory Spring Security requirement. If a system chooses Argon2id/scrypt or a framework uses another pepper policy, evaluate the overall design, upgradeability, and corresponding security guidance.

## 5. Workflow combining HMAC pepper and BCrypt

With a **pepper-before-password-hash** approach, the registration flow is:

~~~text
New password supplied by user
  |
  v
UTF-8 bytes of password (no implicit trim/lowercase)
  |
  v
HMAC-SHA-256(key = SECRET_PEPPER_V1, message = passwordBytes)
  |
  v
Base64URL(HMAC output), 43 ASCII characters
  |
  v
BCryptPasswordEncoder.encode(hmacText)
    -> BCrypt generates random salt + computes slow hash
  |
  v
SAVE TO DB:
  pepper_id = "v1"           (non-secret version label)
  password_hash = "$2a$..."  (salt/cost/hash inside)
DO NOT SAVE SECRET_PEPPER_V1 TO DB
~~~

Login verification flow:

~~~text
User sends username/password over protected channel (HTTPS)
  |
  v
Look up password_hash + pepper_id record
  |
  v
Read secret matching pepper_id from managed secret store
  |
  v
candidate = Base64URL(HMAC(pepperKey, UTF8(password)))
  |
  v
BCryptPasswordEncoder.matches(candidate, password_hash)
  |
  +-- false -> authentication fails
  |
  +-- true  -> password valid under hash and active pepper;
               continue checking account state, MFA, authorization...
~~~

In Spring Security, `PasswordEncoder` is the standard integration point for hashing and verifying passwords. When implementing pepper yourself, ensure **both `encode` and `matches` use the same scheme**, the same byte conversion, the same format, and the exact same key version. When running multiple application instances, every instance must be able to verify records created by all other instances.

### Why must you track pepper versions?

When rotating pepper from `v1` to `v2`, old hash records still need to be verified using **v1** until migrated or reset. Tagging a **non-secret** `pepper_id` identifies which key was used. If you only store the hash and swap a single environment variable, most users who have not changed their password will lose the ability to log in after rotation.

Storage layouts can use two columns:

~~~text
username       pepper_id       password_hash
alice          v2              $2a$...
bob            v1              $2a$...
~~~

Or a **versioned, parser-controlled** password hash format such as `pepper-v1:$2a$...`. Do not confuse `pepper_id` (merely a reference label) with the secret value; never put the base64 secret in the version name.

### What not to do

- Do not use `SHA256(password)` instead of BCrypt just because salt/pepper are present.
- Do not share one fixed salt across all accounts.
- Do not store the pepper secret in the `users` table, in Git-committed configs, or in responses/logs.
- Do not print the HMAC output or password to logs; the HMAC output is a **sensitive input** to the password hash and must not leak.
- Do not reuse a JWT signing key as a pepper; **separate keys by purpose** and access scope.
- Do not treat salt as a pepper or place the pepper on the client; they are distinct concepts.
- Do not use a short/human-readable secret like `"myPepper123"`. Pepper must be high-entropy random bytes generated by a cryptographically secure RNG.

## 6. Managing pepper and server-side secrets properly

### 6.1. Where is the secret generated?

A pepper should be generated by a **CSPRNG** such as `SecureRandom` or a KMS/HSM key generator, with sufficient key length. For HMAC-SHA-256, 32 random bytes is a convenient choice. The secret must **not** be invented by a human and typed into a config file.

OpenSSL example in a development environment:

~~~bash
openssl rand -base64 32
~~~

This command **prints the Base64 secret to the terminal**; run it only when terminal display/history/logging is controlled. For production, generate secrets directly via your organization's secret manager/KMS/HSM, avoiding manual copy-paste or leaving copies in tickets/chat.

### 6.2. Where to store and where not to store

Common practices in real systems:

- Use a **secret manager** with IAM/access policies and auditing, or KMS/HSM when design requires keys never leaving a protected boundary.
- Grant applications access **only to the specific secrets needed**, following least privilege; isolate dev/staging/production environments.
- Use workload identity or short-lived credentials instead of hardcoded credentials to fetch secrets.
- Deliver secrets to instances over secure channels and hold them in memory **only as needed**, limiting users/processes with read permission.
- Monitor secret access and maintain a playbook for suspected compromise; protect backups/snapshots and secret manager admin permissions as well.

An environment variable like `PASSWORD_PEPPER_B64` **can be used for demos and some deployment setups**, though it should not be treated as "100% secure" in every environment: environment variables can leak via process inspection, crash dumps, diagnostic output, host admin access, or orchestrator configs. Protection depends on the runtime platform. In production, prefer an appropriate secret manager and review how secrets are injected, read permissions, and logging.

**Never put** pepper in:

~~~yaml
# DO NOT use this to store real secrets in committed files.
password:
  pepper: "plaintext-secret-goes-here"
~~~

The YAML snippet above is an **illustrative anti-pattern**, not a recommended configuration.

### 6.3. Why does a single shared pepper carry risk?

If the entire system shares one key, losing that key can affect **every account**. Partitioning secrets by environment, application, or appropriate data boundaries can reduce blast radius at the cost of operational complexity. You do not need an independent pepper per user just to mimic salt; if attempted, it requires rock-solid key mapping/rotation and careful evaluation of real benefit over existing mechanisms.

Pepper requires a rotation/recovery strategy. If the secret is lost without a valid managed backup, password hashes peppered with that secret **cannot be verified** under this pre-HMAC scheme, even if the DB remains intact. That is a critical reason to have policy-compliant backups/key escrow, recovery access controls, and a forced password-reset playbook when verification becomes impossible.

### 6.4. Rotating pepper: adding a new key does not auto-update old hashes

Suppose the DB holds records using `v1` and the goal is to migrate to `v2`:

1. Generate a new `v2` secret via CSPRNG, store it in the secret manager, and grant read access as needed.
2. Deploy a verifier that can read **both v1 and v2** during the transition window; the encoder for new passwords defaults to **v2**.
3. When a user logs in successfully against a `v1` record and the raw password is present, verify with `v1`, then **create a new hash** with `v2`, a fresh salt/appropriate cost, and save `pepper_id=v2`.
4. Use safe updates under concurrent login/password changes—such as a `WHERE old_password_hash = ...` condition or record version—to avoid overwriting newer data.
5. Track how many records remain on `v1`; accounts that do not log in during the transition window may require a policy-driven password reset flow.
6. Delete/revoke `v1` only once certain no records still need `v1` verification **or a reset/recovery plan covers them**. If `v1` is compromised, execute incident response rather than keeping it indefinitely just to avoid password changes.

This is **application migration logic**, not an automatic feature triggered merely by calling `PasswordEncoder.upgradeEncoding`. Spring Security has hooks around password hash upgrades in certain flows, but the application must build versioned pepper handling and store/swap keys properly.

### 6.5. Why can't you "re-key in bulk" by reading old hashes?

With the scheme:

~~~text
stored = BCrypt(Base64URL(HMAC(oldPepper, rawPassword)), randomSalt)
~~~

the server **cannot recover `rawPassword`** from the stored BCrypt hash. You cannot compute `HMAC(newPepper, rawPassword)` without knowing `rawPassword`. Therefore you cannot rehash `v1 → v2` purely **offline** from the database alone. You must rely on the password provided by the user on a successful login or an identity-verified password reset flow.

Some *post*-hash pepper architectures have different migration properties, though they require examining the exact storage/verification layout and threat model—never assume simply swapping a secret leaves all stored hashes verifiable.

## 7. Runnable Java 17+ example: PasswordEncoder with pepper before BCrypt

This example is a Java console program using **Spring Security Crypto** with a custom `PasswordEncoder`. It demonstrates three exact points:

1. Pepper is **32 random bytes** supplied via the runtime environment; never hardcoded.
2. Password input passes through **HMAC-SHA-256**, then **Base64URL** into BCrypt (43 ASCII characters, avoiding BCrypt's 72-byte limit).
3. BCrypt generates a **unique random salt on each encode**; the same password with the same pepper still yields two different hashes, and both still verify.

The runnable sample here uses **one key version `p1`** to focus on the encode/verify flow. Rotation requires storing multiple versions and conditional upgrades as in section 6.4; **never just edit the `p1` string in code and swap the secret**.

### 7.1. File structure

~~~text
pepper-demo/
├── pom.xml
└── src/main/java/demo/PepperDemo.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>pepper-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-crypto</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-jcl</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**`src/main/java/demo/PepperDemo.java`**

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import java.util.Base64;
import java.util.Objects;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PepperDemo {

    private static final String PEPPER_VERSION = "p1:";
    private static final String PEPPER_ENV = "PASSWORD_PEPPER_B64";

    private static final class PepperedEncoder implements PasswordEncoder {
        private final BCryptPasswordEncoder bcrypt =
            new BCryptPasswordEncoder(10);

        private final SecretKeySpec hmacKey;

        private PepperedEncoder(byte[] pepper) {
            if (pepper == null || pepper.length != 32) {
                throw new IllegalArgumentException(
                    "Pepper must be exactly 32 random bytes");
            }
            // SecretKeySpec copies byte[] per its API.
            this.hmacKey = new SecretKeySpec(pepper, "HmacSHA256");
        }

        // BCrypt input is always Base64URL of the 32-byte HMAC:
        // 43 ASCII characters, independent of raw UTF-8 string length.
        private String keyedInput(CharSequence rawPassword) {
            Objects.requireNonNull(rawPassword, "rawPassword");
            byte[] rawBytes = rawPassword.toString()
                .getBytes(StandardCharsets.UTF_8);
            byte[] digest = null;
            try {
                Mac hmac = Mac.getInstance("HmacSHA256");
                hmac.init(hmacKey);
                digest = hmac.doFinal(rawBytes);
                return Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(digest);
            } catch (GeneralSecurityException ex) {
                throw new IllegalStateException("HMAC-SHA-256 unavailable", ex);
            } finally {
                Arrays.fill(rawBytes, (byte) 0);
                if (digest != null) {
                    Arrays.fill(digest, (byte) 0);
                }
            }
        }

        @Override
        public String encode(CharSequence rawPassword) {
            return PEPPER_VERSION + bcrypt.encode(keyedInput(rawPassword));
        }

        @Override
        public boolean matches(CharSequence rawPassword,
                               String encodedPassword) {
            if (encodedPassword == null ||
                !encodedPassword.startsWith(PEPPER_VERSION)) {
                return false; // Unknown/missing pepper scheme is rejected.
            }
            String bcryptHash =
                encodedPassword.substring(PEPPER_VERSION.length());
            return bcrypt.matches(keyedInput(rawPassword), bcryptHash);
        }

        @Override
        public boolean upgradeEncoding(String encodedPassword) {
            if (encodedPassword == null ||
                !encodedPassword.startsWith(PEPPER_VERSION)) {
                return true; // App must have migration logic for other schemes.
            }
            return bcrypt.upgradeEncoding(
                encodedPassword.substring(PEPPER_VERSION.length()));
        }
    }

    public static void main(String[] args) {
        String secretB64 = System.getenv(PEPPER_ENV);
        if (secretB64 == null || secretB64.isBlank()) {
            throw new IllegalStateException(
                "Set PASSWORD_PEPPER_B64 to Base64 of 32 random bytes");
        }

        byte[] secret = Base64.getDecoder().decode(secretB64);
        try {
            PasswordEncoder encoder = new PepperedEncoder(secret);
            String stored1 = encoder.encode("correct-horse-example");
            String stored2 = encoder.encode("correct-horse-example");

            System.out.println("correct password: " +
                encoder.matches("correct-horse-example", stored1));
            System.out.println("wrong password: " +
                encoder.matches("wrong-password", stored1));
            System.out.println("same encoded hash: " +
                stored1.equals(stored2));
            System.out.println("stored scheme: " +
                stored1.substring(0, PEPPER_VERSION.length()));
        } finally {
            // Reduce the duration a key copy stays in the local array.
            Arrays.fill(secret, (byte) 0);
        }
    }
}
~~~

**Design explanation:**

- `PepperedEncoder` implements `PasswordEncoder`, so it can be registered as a `@Bean PasswordEncoder` in an application using `DaoAuthenticationProvider`/`UserDetailsService`, provided the stored hash format and key versions are designed consistently.
- `PEPPER_VERSION` is just a **non-secret** version label at the start of the stored string; the `PASSWORD_PEPPER_B64` secret is never saved into the hash.
- `matches` **does not** call `encode(raw).equals(stored)`. BCrypt generates a new salt on each `encode`, so you must use `bcrypt.matches(...)` to verify against the salt embedded in the stored hash.
- `HmacSHA256` produces a 32-byte binary output; unpadded Base64URL has exactly **43 ASCII characters**, so the input passed to BCrypt avoids traditional bcrypt's ~72-byte trap.
- `Mac` is instantiated fresh on every call instead of sharing a mutable `Mac` across requests; this cleanly avoids concurrency hazards.
- `upgradeEncoding` in the example only asks BCrypt about cost and flags unfamiliar schemes for upgrade. It **does not automatically implement** multi-pepper-key migration. Supporting version `p2` requires a version→secret map, a way to verify old hashes, and rehashing when the raw password is available.
- `Arrays.fill` only clears **byte arrays under your control**. Java `String`, environment variables, JVM memory, and internal copies are not guaranteed to be wiped completely; the snippet does not claim keys cannot appear in a memory dump.

**Example limitations:** this is a console model for developers learning `PasswordEncoder`; it does not implement HTTP login/sessions/user databases, brute-force rate testing, or production rotation mechanics. In a real system, check secret availability, fail-closed policies, audit/metrics, and concurrency handling during hash upgrades.

### 7.2. Generating a demo pepper and running

**Linux/macOS shell** (learning environment only; avoid printing real secrets to terminals/logs):

~~~bash
export PASSWORD_PEPPER_B64="$(openssl rand -base64 32)"
mvn -q compile exec:java -Dexec.mainClass=demo.PepperDemo
~~~

The command generates a random secret and keeps it in the current shell's environment variable; Java reads it via `System.getenv`. Never pass secrets directly as command-line arguments because command lines can be recorded in process lists and command histories. In production, do not generate a new key on every app start, as that renders old hashes unverifiable.

**Windows PowerShell** (local example):

~~~powershell
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$key = New-Object byte[] 32
$rng.GetBytes($key)
$env:PASSWORD_PEPPER_B64 = [Convert]::ToBase64String($key)
[Array]::Clear($key, 0, $key.Length)
$rng.Dispose()
mvn -q compile exec:java "-Dexec.mainClass=demo.PepperDemo"
~~~

The two snippets above are two ways to prepare **a temporary demo secret**. When swapping the secret in subsequent runs, `PepperedEncoder` can verify hashes created **during runs with the same secret**; if the application persists hashes across runs, the key must be kept stable and managed securely. Never copy a demo secret into source code to "fix" a lost key.

**Expected output** (independent of the random pepper value as long as all calls happen in one successful run):

~~~text
correct password: true
wrong password: false
same encoded hash: false
stored scheme: p1:
~~~

Because BCrypt generates a random salt, `stored1` and `stored2` will **differ with overwhelming probability** even with the same input and pepper. The program prints neither the secret nor the stored hash to avoid confusing demo output with shareable data.

### 7.3. How to integrate into Spring Security Servlet?

In a Spring Boot Servlet application, the basic integration point is:

~~~java
@Configuration
class PasswordConfiguration {

    @Bean
    PasswordEncoder passwordEncoder(PepperSecretProvider secrets) {
        return new PepperedPasswordEncoder(
            secrets.activeKeyId(),
            secrets.availableVerificationKeys()
        );
    }
}
~~~

This is an **architectural pattern / Java-typed pseudocode**, not a standalone compilable class: `PepperSecretProvider` and a multi-version `PepperedPasswordEncoder` are not defined in the demo project. Do not copy this snippet expecting it to run as is. It highlights that a production encoder should receive keys from a secret provider with clear ACLs, store the version inside the stored value, and know how to verify valid versions during migration.

`DaoAuthenticationProvider` uses `PasswordEncoder.matches(raw, stored)` to verify when a user is loaded from `UserDetailsService`. The application must ensure that new password registration, password changes, and user loading all use **the exact same scheme**. With `DelegatingPasswordEncoder` or a store using `{bcrypt}` prefixes, design a valid prefix order and avoid mis-wrapping that causes "There is no PasswordEncoder mapped for id" errors. Do not migrate legacy data to a new prefix by editing strings alone; hashes must be computed with the right input, secret, and algorithm.

If an application uses `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, the `{bcrypt}` prefix is an **algorithm identifier** for the delegating encoder, **distinct** from `pepper_id`, which is the application's secret identifier. Both version types can be supported, provided the parser, encode/verify ordering, and migration are clearly defined; never treat the two prefixes as the same thing.

## 8. Comparing options when designing a real system

### 8.1. No pepper + strong BCrypt may already be sufficient

Many systems using `BCryptPasswordEncoder` with internal random salts, an appropriate cost, HTTPS, MFA, rate limiting, DB protection, and sound password policies already have a solid design. Pepper is not a requirement for Spring Security to authenticate properly.

Questions to ask before adding a pepper:

1. Does the threat model include **DB leak while runtime/secret manager remain uncompromised**?
2. Can the operations team safely manage key lifecycle, backups, rotation, and key-loss recovery?
3. Is it feasible to execute policy-driven password migration/reset?
4. Do you have testing and monitoring to ensure every instance shares the exact same key versions?
5. Do the defensive gains outweigh the risks of added pepper complexity and misconfiguration?

If you lack secret-management capability, **do not invent a pepper and hardcode it into the same repository**. Doing so provides little protection if the repository leaks and introduces another point of failure.

### 8.2. Why is evaluating the right algorithm still necessary?

Argon2id is a modern password hashing choice with memory/time parameters; scrypt also offers memory-hard properties; BCrypt is widely deployed with strong Spring Security support; PBKDF2 sometimes fits specific compliance/environment requirements. Choose an algorithm based on security policy, library availability, implementation quality, and benchmarks. **Pepper does not turn fast SHA-256 into a modern password hash.**

With BCrypt, implementation variants have limits on long strings and encoding; the HMAC → Base64URL → BCrypt pipeline above deliberately produces a 43-byte ASCII input. Still, that **does not** fix overly weak passwords or inconsistent input policies.

### 8.3. Operational cost and DoS attacks

Adaptive password hashing intentionally consumes CPU/memory. A pepper HMAC is usually cheaper than BCrypt, yet bcrypt verification still consumes resources. Attackers can flood requests to exhaust CPU, so login endpoints must have throttling/rate limiting, monitoring, input limits, and capacity planning. Setting an extreme cost does not mean better security if the server collapses under load.

Do not silently trim/lowercase passwords before hashing; if Unicode normalization or length limits exist, align them clearly with UX and keep `encode` and `matches` identical. Never store or log raw passwords to debug encoding errors. Overly long password inputs should have a reasonable bound to protect the system from excessive resource consumption, while avoiding unnecessarily short password caps.

## 9. Implementation and troubleshooting checklist

### On registration or password change

1. Receive passwords over HTTPS; never log raw values or secrets.
2. Validate password policy at the appropriate layer.
3. If using a pepper, fetch the **active key/version** from a trusted secret store.
4. Apply HMAC/preprocessing consistently; never concatenate strings arbitrarily.
5. Call adaptive `PasswordEncoder.encode(...)`; let BCrypt generate the salt.
6. Store version + hash; never store raw passwords, a separate salt is unnecessary for BCrypt, and **never store the pepper** in the DB.
7. On password change, handle old sessions/tokens per policy and audit the event without leaking secrets.

### On login

1. Load the user record and read the right `pepper_id`/scheme.
2. Fetch the matching valid secret version (never blindly try arbitrary keys indefinitely).
3. Recompute the HMAC input from the raw password and call `BCryptPasswordEncoder.matches` against the stored hash.
4. Handle failed authentication with consistent responses, never exposing internal state or key IDs to unauthorized clients.
5. If verification succeeded under an old key/cost, consider upgrading the hash with the new secret/cost and saving safely.
6. Continue checking account status, MFA, sessions, and authorization at the appropriate layers.

### Common mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Hashes of the same password differ → assumed to be a bug | BCrypt generates a new salt automatically | Use `matches`; never compare `encode(raw)` to the old hash |
| Storing salt in code as a constant | Salt lacks randomness/per-hash uniqueness | Let the encoder generate salts automatically |
| Placing pepper in the user table | A DB leak exposes the pepper too | Separate the secret from hash data |
| Hardcoding pepper in committed `application.yml` | A repo leak defeats the pepper | Use a secret manager and proper injection |
| Rotating key without versioning hashes | Old users cannot verify | Version keys, migrate on login or reset |
| Directly concatenating `password + pepper` before BCrypt | Hits input/encoding limits and design flaws | Use a well-defined scheme such as HMAC → Base64URL → BCrypt |
| Using pepper instead of salt | Lacks per-hash unique salt | Random salt remains mandatory |
| Using `SHA256(password + salt + pepper)` | Fast hash is easy to brute-force offline if secret leaks | Use adaptive password hashing with cost |
| Logging HMAC output | HMAC output is sensitive input to BCrypt | Never log secrets or preprocessing outputs |
| Treating environment variables as 100% secure | Exposed via runtime/process/configs | Evaluate the platform; prefer secret manager/IAM |
| Sharing the same key for JWT and pepper | Expands blast radius and tangles rotation policies | Separate keys by purpose |
| Losing pepper with no recovery | Password hashes become unverifiable | Design backups/versioning/forced resets |
| Old tokens still log in after password change | Password hash does not auto-revoke tokens | Design session/token revocation if needed |

### When pepper compromise is suspected

Quickly determine **key scope**, affected environments/records, whether the attacker also obtained the DB, secret manager access, active tokens/sessions, and runtime control. Then execute incident response per policy: isolate the root cause, rotate keys in a controlled manner, update verifiers and plan rehashes/resets, revoke tokens/sessions as needed, monitor anomalous logins, and notify per requirements. Do not delete the old key impulsively before understanding its impact on account verification.

Distinguish **planned rotation** (old key remains managed during transition) from **compromise-driven rotation** (may require immediate forced resets without trusting the old secret). Keeping a suspected compromised pepper indefinitely just for compatibility can trade away unacceptable security.

## 10. Knowledge self-check

**Q1.** Why do two accounts with the same password have different BCrypt hashes?

**Ans:** Each `encode` uses a distinct random salt and stores salt/cost with the output hash; the two hashes differ with very high probability.

**Q2.** Does salt have to be stored in KMS like pepper?

**Ans:** No. Salt does not need to be secret and is usually embedded in the BCrypt hash. Pepper is an external secret outside the DB if the system chooses to apply one.

**Q3.** When an attacker steals the DB without the pepper, how can pepper help?

**Ans:** It adds a barrier against offline candidate password guessing under the keyed scheme, provided the pepper is strong and well protected. It does not stop other attack vectors or DB+key compromise.

**Q4.** Why should you not naively concatenate a long `password + pepper` string and pass it to BCrypt?

**Ans:** It easily hits BCrypt's ~72-byte input limit and encoding pitfalls, preventing the pepper from taking effect as intended. The HMAC → Base64URL → BCrypt scheme provides a fixed ASCII input that is easier to control.

**Q5.** When rotating pepper v1 to v2, can you update all hashes immediately from the DB alone?

**Ans:** Not for the pre-HMAC-then-BCrypt scheme in this lesson: the raw password is needed to compute the HMAC with the new key. You can rehash on successful user login or require a reset per policy.

**Q6.** How does `PasswordEncoder.matches(raw, stored)` differ from comparing `encode(raw).equals(stored)`?

**Ans:** `matches` verifies using the salt and parameters from the stored hash. `encode` creates a hash with a new salt, so direct string comparison is wrong.

**Q7.** With a pepper, can you use fast SHA-256 instead of BCrypt?

**Ans:** No. Salt/pepper do not replace the costly computation of password hashing designed to resist offline guessing.

**Q8.** Does putting pepper in an environment variable guarantee absolute secrecy?

**Ans:** No. Risks remain from runtime, logs, process inspection, crash dumps, or host administration; production needs proper secret management and least privilege.

**Q9.** When a user logs in with a valid v1 hash, what is the safe upgrade action?

**Ans:** Verify with v1, create a new hash with pepper v2 + fresh salt/cost using the available raw password, and update the record safely; do not merely alter the version text.

**Q10.** What happens if an app deploys 3 instances with three different random peppers?

**Ans:** A password hash created on one instance may fail verification on another. Instances in the same scope must share the exact same managed secret/version; key rotation must be coordinated.

**Remember:** **Random salt is a public part of the password hash, and BCrypt already manages salt. Pepper is a separate server-side secret, added only when backed by a threat model and key-management capability. Every hash must still use an appropriate algorithm; managing, backing up, rotating, and revoking the pepper is just as critical as how it is combined with the password.**