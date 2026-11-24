# Distinguishing Password Hashing from Reversible Encryption

To verify a logging-in user, the application needs to answer one question: **“Does the newly entered password match the password the user registered?”**. The application **does not need to retrieve the old password**. Therefore, login passwords must be stored as a **one-way password hash** using a dedicated algorithm, rather than storing plaintext or a decryptable ciphertext.

Although both transform data into a hard-to-read string, the two mechanisms serve different purposes:

- **Password hashing:** computes a verification value from the password, a salt, and cost parameters. On login, the system uses `PasswordEncoder.matches(rawPassword, storedHash)`; there is no `decrypt(storedHash)` operation to recover the original password.
- **Reversible encryption:** transforms plaintext into ciphertext using an encryption key and appropriate parameters. Anyone with the key can decrypt the plaintext. It should only be used when **the business logic genuinely requires reading the original content back**.
- **Encoding such as Base64:** only changes the representation of bytes into text; anyone can decode it. It is neither encryption nor password hashing.

This lesson targets **Java 17+, Spring Boot 3, Spring Security 6.x, Spring MVC/Servlet**, combining the `PasswordEncoder`, `BCryptPasswordEncoder`, and `DelegatingPasswordEncoder` APIs, a sample Spring Security application, tests, and a standalone Java 17 program comparing PBKDF2 with AES-GCM. If your environment uses Spring Security 7 or a reactive stack, consult the documentation for that exact version and stack.

## 1. Comparing the Two Protection Types by Purpose

| Criterion | Dedicated Password Hashing | Reversible Encryption |
| --- | --- | --- |
| Purpose | Verify a re-entered password | Keep data confidential while still recoverable |
| Typical algorithms | Argon2id, scrypt, bcrypt, PBKDF2-HMAC-SHA256 | AES-GCM (authenticated encryption) |
| Input data | Raw password + salt + cost parameters | Plaintext + encryption key + nonce/IV |
| Output | Stored hash + metadata | Ciphertext + nonce/IV + authentication tag |
| Can original plaintext be decrypted? | **No** | **Yes, with the right key** |
| Salt | Random per password; can be stored alongside the hash | Does not use salt in the same sense; GCM uses a nonce/IV |
| Secret key | No encryption key needed; an optional secret pepper may be added | **Must protect the encryption key** |
| Password comparison | `matches(raw, stored)` returns boolean | Could be decrypted to read content; should not be used for storing login passwords |
| Same password for two users | Per-hash salt usually makes stored hashes differ | Different nonces can make ciphertexts differ, but the key can still decrypt them |
| When the DB is leaked | Attackers can test candidate passwords offline, paying the KDF computation cost | If the key is also leaked, attackers can decrypt the data |
| When a user forgets their password | Reset to a new password | Decryption remains possible if the key is still valid |
| Use case | User login passwords | Partner integration secrets that must be resent, data requiring controlled recovery |

A quick decision rule: if you only need to **compare a secret** without reading it back, consider an appropriate hashing/verifier mechanism. If you need to reuse the plaintext under authorized access, encryption may be needed. User login passwords belong to the first category.

### 1.1. Two Distinct Flows

```text
PASSWORD HASHING
raw password + random salt + cost
              |
              v
     Argon2id / bcrypt / scrypt / PBKDF2
              |
              v
       stored password hash
              |
     candidate password ----> matches(...) ----> true / false
              |
       NO decrypt(hash)

REVERSIBLE ENCRYPTION
plaintext + encryption key + IV/nonce
              |
              v
          AES-GCM encrypt
              |
              v
    ciphertext + nonce + auth tag
              |
           AES-GCM decrypt + correct key
              |
              v
        recovered plaintext
```

Password hashing aims to **increase the cost of password guessing when stored data is leaked**, whereas encryption aims to **keep content confidential from anyone without the key**. Both have their roles, but they are not interchangeable.

## 2. “Cannot Decrypt a Hash” Does Not Mean “Cannot Guess a Password”

This is a very common misconception. A password hash does not contain a “secret cipher” that you can decrypt with a key. However, an attacker can **try guessing**:

```text
Alice's leaked storedHash
     |
candidate "123456" -> hash with stored salt -> match?
candidate "password" -> hash with stored salt -> match?
candidate "Alice2026!" -> hash with stored salt -> match?
...
```

If a candidate produces the matching output, the attacker has guessed the password; they did not decrypt the hash. Because human-chosen passwords can be very predictable, the system must make **each guess resource-intensive**.

### 2.1. Why Not Store SHA-256(password)?

SHA-256 is a good cryptographic hash function for many tasks, such as verifying data integrity. However, it is designed to **compute fast**, whereas password hashing must be **intentionally slow**, and typically adjustable in cost as hardware evolves.

| Storage Method | Suitable for Passwords? | Reason |
| --- | --- | --- |
| Plaintext | No | A database leak exposes every password |
| Base64(password) | No | Trivially decoded |
| MD5(password) / SHA-1(password) | No | Fast/legacy hash, unsuitable |
| SHA-256(password) | No | Too fast against offline guessing |
| SHA-256(salt + password) | Insufficient | Salt helps, but guessing speed remains high |
| AES(password, key) | No | Can be decrypted if the key leaks or is misused |
| bcrypt with appropriate salt/cost | Usable | Adaptive password hashing |
| Appropriate scrypt or Argon2id | Usable | CPU/memory cost increases guessing expense |
| PBKDF2-HMAC-SHA256 with proper iterations/salt | Usable | Password-based key derivation with cost |
| Custom-built HMAC-SHA256 | Not sufficient on its own | Secret-key MAC does not substitute for a password KDF |

The word “hash” alone is not enough to conclude a system stores passwords securely. You must know the **algorithm**, **salt**, **cost/work factor**, verification flow, upgrade path, and load controls.

## 3. Salt: Unique Randomness for Each Hash

A **salt** is random data generated for each password hash. The system can store the salt **alongside** the hash result because a salt **does not need to be kept secret**. For the same password belonging to Alice and Bob:

```text
Alice:
password = "same-secret"
salt = random_A
hash = KDF(password, random_A, cost)

Bob:
password = "same-secret"
salt = random_B
hash = KDF(password, random_B, cost)

=> Alice's hash usually DIFFERS from Bob's hash.
```

Salts reduce the value of precomputed lookup tables such as rainbow tables and force attackers to pay the guessing cost separately for each salt. A salt does **not** turn a password hash into ciphertext; the salt is a parameter **for verifying** newly entered passwords later.

### 3.1. Salt Does Not Replace Computational Cost

Assume the attacker knows the salt. This is normal because salts are typically stored in the database. If the application only computes `SHA256(salt || password)`, an attacker can still test huge numbers of candidates. Use a proper password KDF so you get both a salt and a sufficiently high work factor.

### 3.2. Is a Salt an Application Secret?

No. A salt is **different from** a secret key and a pepper. Even when an attacker has both the hash and the salt, they still have to guess the password. You do not need to put salts in a KMS, but you must use a secure random source such as `SecureRandom` as directed by the algorithm/encoder. Never use a single fixed salt for all users.

## 4. Pepper: When Do You Need a Secret Outside the Database?

A **pepper** is an additional secret, typically shared across a scope of users or an application and kept outside the DB (secret store, KMS/HSM/vault) to add defense-in-depth if the DB is leaked. Comparison:

| | Salt | Pepper |
| --- | --- | --- |
| Needs to be secret? | No | **Yes** |
| Unique per hash? | Typically yes | Typically shared |
| Stored with the hash? | Yes | No |
| Goal | Differentiate hashes, prevent precomputation | Add a barrier if the DB is leaked |
| If lost | Stored with the hash, so no issue | May prevent password verification depending on design |
| If leaked | Not a “key compromise” | Requires rotation, migration/reset plan |

A pepper **does not replace** a salt and a slow KDF. Do not invent `SHA256(pepper + password)` and assume it is sufficient. If using a pepper, use an evaluated scheme, operational procedures, and a plan for when the pepper is revoked.

### 4.1. An IV/Nonce Is Not a Salt

AES-GCM uses an **IV/nonce**, not a password salt. In particular, **never reuse a nonce under the same encryption key**, as that can severely break confidentiality and integrity. With a random 96-bit nonce, systems encrypting at large scale must evaluate collision risk and choose an appropriate nonce management strategy.

Both a salt and a nonce can be stored alongside the output, but their **security constraints and purposes are different**. Do not use a fixed IV just because the same application always uses one key.

## 5. Work Factor: Intentional Password Computation Cost

A good password KDF makes each password check consume CPU time, and potentially memory. This imposes a cost on the legitimate server, but it also raises the cost of offline attacks.

- **bcrypt:** configures strength/cost, e.g., 10 or 12; cost rises rapidly as the cost parameter increases.
- **PBKDF2:** configures iteration count, e.g., PBKDF2-HMAC-SHA256 with 600,000 iterations in a current OWASP recommendation; always re-verify current guidance at deployment time.
- **scrypt/Argon2id:** also include memory parameters to resist parallel cracking advantages on specialized hardware.
- **Argon2id:** is the primary choice recommended by OWASP for new systems when properly supported by the environment.

There is no single eternal cost number suitable for every server. Benchmark verification latency on your own infrastructure, assess concurrent logins, rate limits, and DoS risk; increase the cost as hardware evolves while keeping user experience and resource usage reasonable.

### 5.1. Input Length Limit of bcrypt

Many bcrypt implementations process at most about **72 input bytes**. That is bytes, not Java's `String.length()`: a single Unicode character can take multiple UTF-8 bytes. Check the exact rules of your encoder version, and do not silently truncate passwords or arbitrarily invent a pre-hashing step. OWASP documents specific pitfalls when naively combining a fast hash with bcrypt.

## 6. Spring Security PasswordEncoder Is a One-Way API

In `org.springframework.security.crypto.password`, the core contract is:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

This is a simplified declaration for study purposes. There is no `decrypt` or `decode` in `PasswordEncoder`.

- `encode(raw)` is used during registration, setting, or changing a password to generate the stored value.
- `matches(candidate, stored)` is used on login, taking the newly entered candidate and the existing stored hash and returning true/false.
- `upgradeEncoding(stored)` helps check whether the algorithm/cost needs upgrading; updating the database also requires an appropriate flow and storage.

### 6.1. BCryptPasswordEncoder: Correct Matching Example

```java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);

String storedHash = encoder.encode("local-only-password");

boolean valid = encoder.matches(
    "local-only-password", storedHash
);
boolean invalid = encoder.matches(
    "wrong-password", storedHash
);

// valid == true, invalid == false
```

This is a snippet requiring Spring Security dependencies and imports. Strength 12 is only an example; benchmark on your server. The output of `encode` contains a random salt, so encoding the same raw password twice usually produces different Strings.

**Common anti-pattern:**

```java
// Wrong: a new encode may use a new salt, so String comparison fails.
boolean wrong = encoder.encode(raw).equals(storedHash);

// Correct: the encoder uses the stored hash's metadata/salt.
boolean correct = encoder.matches(raw, storedHash);
```

The parameter name `encodedPassword` in the API does not mean “an encrypted password that can be decrypted.” For a one-way encoder, it is the formatted hash used for matching.

### 6.2. Why Must Stored Hashes Still Be Protected?

A stored hash is not plaintext, but if leaked it still lets attackers guess passwords offline. Never log password hashes, never send them to the browser, never leave backups public, and never grant overly broad read access to the `password_hash` column.

## 7. DelegatingPasswordEncoder: Identifying Hash Formats Over Time

Spring Security provides `DelegatingPasswordEncoder` to support multiple algorithms/costs when migration is needed:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
```

With Spring Security 6.5 and the default factory, new hashes typically use bcrypt with the `{bcrypt}` prefix. General format:

```text
{id}encodedPassword
```

Examples:

```text
{bcrypt}$2a$10$...
{pbkdf2}...
{scrypt}...
```

`id` is not an encryption key. It is the **delegate name** so `matches` knows how to interpret the rest. Because password storage best practices evolve over time, this metadata supports a transition period where old and new hashes coexist.

### 7.1. Format Verification Example

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String saved = encoder.encode("sample-password");

System.out.println(saved.startsWith("{bcrypt}"));
System.out.println(encoder.matches("sample-password", saved));
System.out.println(encoder.matches("wrong", saved));
```

With the factory in the Spring Security version illustrated here, the expected boolean outputs are:

```text
true
true
false
```

The exact hash string changes with the random salt, so do not hardcode that value as a fixed output. When upgrading the framework or changing the encoding id configuration, verify behavior against your actual BOM.

### 7.2. If You Encounter “id null”

Legacy bcrypt hashes may be stored directly starting with `$2a$...`, whereas `DelegatingPasswordEncoder` expects an `{id}` prefix. Without an appropriate mapping, `matches` may throw:

```text
There is no PasswordEncoder mapped for the id "null"
```

Do not fix this with `NoOpPasswordEncoder` or by disabling password verification. Identify the exact legacy format and plan a migration/prefix/hash upgrade with tests, preserving verification for legitimate users.

### 7.3. Upgrading the Algorithm When a User Logs In

Once a password is verified successfully, the application can check `upgradeEncoding` and regenerate a hash with the new parameters from the **raw password the user just submitted**. `UserDetailsPasswordService` can help update the encoded password within the provider flow when properly configured. You cannot bulk-decrypt all legacy password hashes and rehash them without the raw passwords.

## 8. When Is Reversible Encryption Appropriate?

For example, an application needs to send a credential to a third party in an outbound request. The application is authorized to read the original content to connect, so authenticated symmetric encryption with proper key management can be appropriate.

Some use cases:

- Integration secrets that the backend must reuse under controlled authorization;
- Personal data/sensitive documents that must be read back under legitimate requirements;
- Data fields used in a business flow requiring exact recovery;
- Backups protected by a separate encryption key.

**Do not use encryption to provide a “view registered password” feature.** That is not a requirement of a password authentication system. Password reset is the right model.

### 8.1. AES-GCM Is Authenticated Encryption

AES-GCM both protects confidentiality and detects tampering of the ciphertext or associated data via an authentication tag. When using it, you must:

1. Generate and protect the encryption key securely;
2. Never reuse a nonce with the same key;
3. Use appropriate IV/tag lengths and algorithms;
4. Verify the tag on decryption and reject if invalid;
5. Use AAD to bind data to a tenant/account/type when needed;
6. Manage key versions, rotation, KMS/backups, and decryption permissions.

Never use AES-ECB or combine AES-CBC with a homegrown “integrity check.” With GCM, a single nonce-reuse bug can have catastrophic consequences.

### 8.2. Value Classification Table

| Value | Secret? | How Should It Be Stored? |
| --- | --- | --- |
| Password salt | No | Alongside the password hash |
| Password KDF cost/id | No | Alongside the stored hash |
| Password hash | Must be protected because it can be guessed offline | Dedicated DB column, narrow access permissions |
| Pepper | **Yes** | Outside the DB, in a secret manager |
| AES-GCM nonce/IV | Usually no | Alongside the ciphertext, ensuring uniqueness |
| AES-GCM ciphertext/tag | Per data policy | Stored alongside metadata needed to decrypt |
| AES encryption key | **Yes** | KMS/HSM/vault, not stored under the same DB permissions |
| Raw password | **Yes** | Never log/write plaintext, minimize lifetime in memory |

If an attacker obtains both the DB ciphertext and the AES key, they can decrypt it. If an attacker only obtains a DB containing properly created password hashes, they have no “decryption key,” though they can still attempt offline guessing. The two threat models are not the same.

## 9. Standalone Java 17: PBKDF2 Matching vs. AES-GCM Decryption

The following program **does not require Spring Security**. It demonstrates both operations on the same JDK 17:

- PBKDF2WithHmacSHA256: derives a hash from raw password + random salt + iterations, then uses `MessageDigest.isEqual` to compare candidate passwords.
- AES/GCM/NoPadding: encrypts a byte sequence with a secret key + random nonce; then decrypts to recover the original content and detects a modified tag.

**Limitations:** This is educational code, not a production password storage system. A real product also needs schema/metadata, raw input protection, cost benchmarking, error controls, KMS, request rate limiting, auditing, migration, and reset flows. With Spring Security, prefer the built-in `PasswordEncoder`.

### 9.1. Complete Code

Create `HashVsEncryption.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;

import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.PBEKeySpec;

public class HashVsEncryption {
    private static final int ROUNDS = 600_000;
    private static final int SALT_BYTES = 16;
    private static final int KEY_BITS = 256;
    private static final int IV_BYTES = 12;
    private static final int TAG_BITS = 128;

    record PasswordRecord(byte[] salt, byte[] hash) {}
    record CipherRecord(byte[] iv, byte[] ciphertextAndTag) {}

    static byte[] derive(char[] password, byte[] salt)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(
            password, salt, ROUNDS, KEY_BITS
        );
        try {
            return SecretKeyFactory
                .getInstance("PBKDF2WithHmacSHA256")
                .generateSecret(spec)
                .getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static PasswordRecord hash(char[] password, SecureRandom rng)
            throws GeneralSecurityException {
        byte[] salt = new byte[SALT_BYTES];
        rng.nextBytes(salt);
        return new PasswordRecord(salt, derive(password, salt));
    }

    static boolean matches(char[] candidate, PasswordRecord saved)
            throws GeneralSecurityException {
        byte[] value = derive(candidate, saved.salt());
        try {
            return MessageDigest.isEqual(value, saved.hash());
        } finally {
            Arrays.fill(value, (byte) 0);
        }
    }

    static CipherRecord encrypt(byte[] plain, SecretKey key,
            SecureRandom rng) throws GeneralSecurityException {
        byte[] iv = new byte[IV_BYTES];
        rng.nextBytes(iv);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
            new GCMParameterSpec(TAG_BITS, iv));
        return new CipherRecord(iv, cipher.doFinal(plain));
    }

    static byte[] decrypt(CipherRecord record, SecretKey key)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
            new GCMParameterSpec(TAG_BITS, record.iv()));
        return cipher.doFinal(record.ciphertextAndTag());
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        SecureRandom rng = new SecureRandom();
        char[] password = "educational-secret".toCharArray();
        char[] wrong = "other-secret".toCharArray();

        try {
            PasswordRecord record = hash(password, rng);
            System.out.println("hash.saltBytes="
                + record.salt().length);
            System.out.println("hash.correct="
                + matches(password, record));
            System.out.println("hash.wrong="
                + matches(wrong, record));

            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(128, rng);
            SecretKey key = generator.generateKey();

            byte[] plain = "retrievable-data".getBytes(
                StandardCharsets.UTF_8
            );
            CipherRecord encrypted = encrypt(plain, key, rng);
            byte[] restored = decrypt(encrypted, key);

            System.out.println("aes.roundTrip="
                + Arrays.equals(plain, restored));

            byte[] modified = encrypted.ciphertextAndTag().clone();
            modified[modified.length - 1] ^= 1;

            boolean rejected = false;
            try {
                decrypt(new CipherRecord(
                    encrypted.iv(), modified), key);
            } catch (AEADBadTagException expected) {
                rejected = true;
            }

            System.out.println("aes.tamperRejected=" + rejected);
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
```

Run with JDK 17:

```bash
javac HashVsEncryption.java
java HashVsEncryption
```

**Expected stdout strictly following the program logic:**

```text
hash.saltBytes=16
hash.correct=true
hash.wrong=false
aes.roundTrip=true
aes.tamperRejected=true
```

The program **does not print** the actual salt, hash, key, IV, or ciphertext, so these lines do not vary with random input. On a Java 17 provider supporting the standard algorithms used, a tampered GCM tag will be rejected with `AEADBadTagException`.

### 9.2. Reading the Results Correctly

- `PasswordRecord` stores **salt + derived hash**. `matches` takes the stored salt and tests the candidate; there is no password decryption.
- `MessageDigest.isEqual` is used to compare byte arrays in a manner more appropriate than `Arrays.equals` for sensitive authentication data.
- PBKDF2 uses iterations to increase the cost of guessing passwords. 600,000 is only an illustrative parameter from one guideline at the time of writing, not a substitute for benchmarking or policy.
- `KeyGenerator` generates a **128-bit** AES key for illustration; in production you must manage keys with recovery and protection.
- `AES-GCM` uses a 12-byte random IV and a 128-bit tag; calling `decrypt` with the right key/IV recovers the plaintext.
- Flipping the last byte of the ciphertext/tag causes tag verification to fail. Never swallow the exception and return unauthenticated data.
- `char[]` is zeroed out in `finally`, though literal passwords embedded in source/class files are only suitable for demos; never hardcode real secrets.
- In systems encrypting large volumes of data, you must guarantee nonce uniqueness under the same key; a random 96-bit nonce is not an absolute guarantee against collisions under unbounded use.

### 9.3. What Happens If the Key Is Lost?

If the encryption key is lost, AES-GCM ciphertext may no longer be decryptable. If the key is leaked along with the ciphertext, whoever has the key can read the data. That is why encryption requires a KMS, key rotation, least-privilege access, and separate backup/recovery plans.

Password hashes have no analogous decryption key. When a user forgets their password, the system uses a reset flow; it does not depend on a master key to “unlock” every password.

## 10. Spring Boot 3: Password Storage with PasswordEncoder

The following example uses HTTP Basic to clearly show that passwords are stored as hashes; during authentication, the framework **matches** the raw password against the stored hash rather than decrypting it. Code targets **Spring MVC/Servlet, Spring Boot 3, and Spring Security 6.x, Java 17+**.

Two demo users:

| Account | Local Password | Role |
| --- | --- | --- |
| `reader` | `reader-demo-pass` | `ROLE_USER` |
| `admin` | `admin-demo-pass` | `ROLE_USER` and `ROLE_ADMIN` |

Endpoint `GET /public` is public; `GET /api/me` requires login; `GET /api/admin` requires the admin role; other requests are denied.

### 10.1. Gradle Dependencies

In the `build.gradle` Groovy DSL of a Spring Boot 3 project with plugin/repository configuration:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is only the dependencies block. With Maven, use the equivalent starters and `spring-security-test` in test scope. Do not manually mix Spring Security versions incompatible with the Boot BOM.

### 10.2. Main Class

Create `src/main/java/example/passwords/PasswordDemoApplication.java`:

```java
package example.passwords;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasswordDemoApplication.class, args);
    }
}
```

### 10.3. SecurityConfig.java

Create `src/main/java/example/passwords/SecurityConfig.java`:

```java
package example.passwords;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-pass"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Analysis:

1. `PasswordEncoderFactories.createDelegatingPasswordEncoder` creates the encoder; with the Spring Security 6.x default factory, new hashes carry `{bcrypt}`.
2. `encoder.encode` is used only **when creating demo users** to store hashes in the user store; real applications call `encode` upon registration or password change.
3. `UserDetailsService` loads the user/hash and does not compare raw passwords itself.
4. `DaoAuthenticationProvider` integrated with username/password authentication will use `PasswordEncoder.matches` during authentication.
5. `.httpBasic` handles the Basic header; Basic is **Base64**, not secret encryption; production strictly requires HTTPS.
6. `.authorizeHttpRequests` is authorization, independent of hashing. A properly authenticated user may still lack a required role.
7. `anyRequest().denyAll()` denies undeclared routes.
8. Nothing decrypts the stored password hash; `PasswordEncoder` provides no such API.
9. Hardcoded passwords are for localhost only; production requires a user database and proper secret management.

### 10.4. Controller

Create `src/main/java/example/passwords/DemoController.java`:

```java
package example.passwords;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/api/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin");
    }
}
```

The controller receives an `Authentication` already verified by the provider. It does not accept a raw password to compare against the DB itself, does not return password hashes in JSON, and has no decryption functionality.

### 10.5. Running with Gradle

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Assuming the app runs at `http://localhost:8080` for the demo:

```bash
# 200: public endpoint
curl -i http://localhost:8080/public

# 401: Basic credentials not provided
curl -i http://localhost:8080/api/me

# 200: correct reader password
curl -i -u reader:reader-demo-pass http://localhost:8080/api/me

# 401: wrong password, unauthenticated
curl -i -u reader:wrong-pass http://localhost:8080/api/me

# 403: reader is authenticated but lacks ROLE_ADMIN
curl -i -u reader:reader-demo-pass http://localhost:8080/api/admin

# 200: admin has ROLE_ADMIN
curl -i -u admin:admin-demo-pass http://localhost:8080/api/admin
```

These are the **expected** HTTP statuses based on the sample configuration, not logs from an actual run here. Only use demo passwords on localhost. HTTP Basic uses Base64 and `curl -u` can expose credentials in shell history or process lists; real applications must use HTTPS and protect secrets.

## 11. Testing Password Hashes and HTTP Authentication with MockMvc

Add `spring-boot-starter-test` and `spring-security-test` as shown in the dependencies section. Create `src/test/java/example/passwords/PasswordStorageTest.java`:

```java
package example.passwords;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordStorageTest {

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    UserDetailsService users;

    @Autowired
    MockMvc mvc;

    @Test
    void encodedValueIsNotPlaintext() {
        String hash = encoder.encode("sample-password");

        assertThat(hash).startsWith("{bcrypt}");
        assertThat(hash).isNotEqualTo("sample-password");
    }

    @Test
    void matchesChecksCorrectAndIncorrectPassword() {
        String hash = encoder.encode("sample-password");

        assertThat(encoder.matches("sample-password", hash)).isTrue();
        assertThat(encoder.matches("incorrect", hash)).isFalse();
    }

    @Test
    void saltedHashesForSamePasswordUsuallyDiffer() {
        String first = encoder.encode("sample-password");
        String second = encoder.encode("sample-password");

        assertThat(first).isNotEqualTo(second);
        assertThat(encoder.matches("sample-password", first)).isTrue();
        assertThat(encoder.matches("sample-password", second)).isTrue();
    }

    @Test
    void userStoreContainsHash() {
        String stored = users.loadUserByUsername("reader")
            .getPassword();

        assertThat(stored).startsWith("{bcrypt}");
        assertThat(encoder.matches("reader-demo-pass", stored)).isTrue();
    }

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointRejectsAnonymous() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctBasicPasswordAuthenticates() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader-demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"));
    }

    @Test
    void wrongBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void passwordCorrectButRoleMissingIsForbidden()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-demo-pass")))
            .andExpect(status().isOk());
    }
}
```

Run:

```bash
./gradlew test --tests example.passwords.PasswordStorageTest
```

Windows:

```powershell
.\gradlew.bat test --tests example.passwords.PasswordStorageTest
```

**Expectation:** 9 test methods pass in a properly configured Boot 3/Security 6.x project. This is the expected outcome from the source code, **not an execution record**. The test checking that two stored hashes differ relies on a random salt, so mathematically there remains an exceedingly tiny probability of collision. Never hardcode the full hash output; each valid encode call may differ.

| Test | What It Asserts |
| --- | --- |
| Hash differs from raw password | Passwords are not stored in plaintext |
| `matches` true/false | Verifier accepts/rejects without decryption |
| Two new hashes | Salt makes outputs usually differ |
| User store | `UserDetails.getPassword()` is an encoded hash |
| HTTP Basic 200/401 | Provider verifies credentials |
| Reader vs admin | Authorization is independent of password verification |

`@WithMockUser` only creates a mock Authentication in tests and does not prove the password provider works. Use HTTP Basic, form login tests, or call `AuthenticationManager.authenticate` when you want to test real password verification.

## 12. Database Flows: Registration, Login, Password Change, and Reset

### 12.1. Account Registration

```text
HTTPS registration request
        |
        +-- Validate password policy
        +-- Check breached-password list per policy
        +-- PasswordEncoder.encode(rawPassword)
        +-- Store password_hash and account metadata in DB
        +-- Do not store raw password/logs/analytics
```

Example fragment in a service:

```java
String encoded = encoder.encode(request.password());
accountRepository.save(
    new Account(request.username(), encoded)
);
```

This fragment requires a real `Account`, repository, validation, and transaction. Never pass a raw password into SQL and treat `WHERE password = ?` as secure authentication.

### 12.2. Login

```text
Client supplies password
       |
       v
AuthenticationProvider
       |
       +-- UserDetailsService.loadUserByUsername(username)
       |          -> password hash + authorities + flags
       |
       +-- PasswordEncoder.matches(raw, storedHash)
       |
       +-- Account state check (disabled/locked/expired...)
       |
       v
Authentication succeeds or throws exception
```

`UserDetailsService` only loads the user/hash. `DaoAuthenticationProvider` and `PasswordEncoder` check the password; HTTP status 401/302 is handled by the filter/entry point depending on the mechanism. A user with a valid password can still receive 403 if they lack the required authority.

### 12.3. Changing a Password

Flow: verify permission to change the password, re-verify current credentials/MFA if needed, check the new password against policy, call `encode(newPassword)`, update the hash atomically, and consider revoking active sessions/tokens.

Never decrypt the old stored hash, and never send old passwords to support staff.

### 12.4. Forgot Password

True password recovery is a **reset**:

1. The user requests a reset through a valid channel; responses avoid revealing whether the account exists.
2. The server generates a high-entropy random reset token with a short expiration.
3. Store a verifier/token hash and single-use state; send the token through an appropriate channel.
4. When the token is valid, the user sets a **new** password.
5. The server calls `PasswordEncoder.encode` to create a new hash and saves it.
6. The reset token is invalidated, and the system may revoke sessions, audit the event, and send a notification.

There is no step to “decrypt the hash and send the old password.” A reversible encryption scheme designed merely to recover passwords is a design flaw that must be fixed.

## 13. Encryption at Rest and Password Hashing Can Coexist

A system may encrypt its database, backups, or sensitive columns to reduce risk if an attacker only obtains storage media. However, passwords should still be hashed at the application layer. Having disk encryption **does not turn encrypted password ciphertext into a suitable login storage model**.

If the database is leaked:

| Password Storage | Attacker Only Has DB | If Attacker Also Has App Key |
| --- | --- | --- |
| Plaintext | Read directly | No key needed |
| AES-encrypted password | Has ciphertext; may lack key | Can bulk-decrypt |
| SHA-256/password | Very fast offline guessing | No key needed |
| Password KDF + random salt/cost | Offline guessing still possible, but each attempt is costly | No “decryption key”; pepper if used is a separate layer |

Salts are typically public, yet password hashes must still be protected because attackers can brute-force them. Security also requires password policies, MFA, rate limiting, cookie/session protection, TLS, credential stuffing defenses, and **authorization** on actions/data. **CSRF** is also a request-protection layer in cookie/session-based applications depending on the threat model; it does not replace hashing or encryption.

## 14. Common Implementation Mistakes

### 14.1. “Base64-encoding a password means it is encrypted”

No. Base64 is an encoding; a standard decoder recovers the bytes. HTTP Basic also uses Base64 for username/password, which is why it must travel over TLS/HTTPS.

### 14.2. “SHA-256 is fast and strong, so it is the best choice”

SHA-256 is a fast cryptographic hash function; for human passwords, **speed is a disadvantage**. Choose a dedicated password KDF.

### 14.3. “Adding a salt is enough”

A salt prevents duplicate hashes and precomputation, but it does not turn SHA-256 into slow password hashing. You need an appropriate algorithm and cost.

### 14.4. “Having an AES key lets administrators view passwords again”

That capability is unnecessary and amplifies the blast radius if the key leaks. Store password hashes and support resets instead of decryption.

### 14.5. “Two bcrypt encode calls must return the same String”

False because of the random salt. `matches` is the verification API.

### 14.6. “If we lose the pepper, decrypt old hashes and rehash them”

There is no decryption operation. If pepper rotation lacks a login-time migration flow, you may have to trigger password resets.

### 14.7. “No need to protect hashes since they aren’t passwords”

Password hashes are valuable for offline guessing and can reveal algorithm/cost metadata. Restrict access, avoid logging them, and protect backups.

### 14.8. “I can use a fixed AES-GCM IV”

No. Nonce reuse under the same key breaks security properties. A safe nonce strategy is required.

### 14.9. “Just crank bcrypt cost really high to be safe”

High cost increases the expense of every login, which can lead to DoS or poor user experience. Benchmark, cap concurrency, and plan gradual increases.

### 14.10. “NoOpPasswordEncoder fixes the id null error”

`NoOpPasswordEncoder` does not hash passwords, so it is not a production solution. Fix the format/mapping and migration properly.

### 14.11. “Storing the encryption key in the same table is convenient”

If an attacker can read both the ciphertext and the key, encryption loses its purpose. Use a secret manager/KMS, least-privilege access, and a rotation process.

### 14.12. “Password hashing prevents phishing”

Hashing protects passwords stored on the server; it does not prevent phishing, malware, session theft, MFA bypass, or broken role policies. Other defense layers are needed.

### 14.13. “Use the same pepper and salt as the IV”

Salts, peppers, and IVs serve different functions. Never use a single fixed value in place of all three.

### 14.14. “Passwords longer than 72 characters are always safe with bcrypt”

The boundary in many bcrypt implementations is **72 bytes**, not Java character count. Check implementation limits and policy without silently truncating input.

### 14.15. “Decrypt inside the controller to check login”

Controllers should not handle stored passwords. Spring Security authentication filters/providers call `PasswordEncoder.matches`; controllers receive an authenticated principal.

## 15. Security Checklist When Choosing a Storage Mechanism

**Login passwords**

- Do you use `PasswordEncoder`/an adaptive password KDF instead of storing raw or reversibly encrypted passwords for login?
- Are per-hash salts and an appropriate work factor used and benchmarked on your server?
- Do you have tests for `matches` with right/wrong passwords and verify stored hashes are not plaintext?
- Do you have an `{id}` format or other metadata to support migration?
- Are long passwords, Unicode, and algorithm limits handled properly?
- Do you prevent logging passwords, hashes, tokens, and Basic Authorization headers?
- Do you have secure password resets and a session revocation policy?
- Are DB backups protected, `password_hash` read access restricted, and access audited?
- Are rate limiting, MFA, and monitoring aligned with your threat model?

**Data that must be decrypted**

- Does the business need genuinely require recovering the plaintext?
- Are you using a trusted AEAD library like AES-GCM and verifying the tag?
- Do you have KMS/vault/HSM key management, key versioning, rotation, and backups?
- Is nonce uniqueness per key guaranteed rather than hardcoded?
- Is AAD/metadata binding used where needed, especially tenant and owner?
- Are decryption call sites restricted and audited?

**Project verification**

- Verify the exact Spring Boot/Security version in your Gradle/Maven dependency graph.
- Run JUnit/MockMvc tests for right/wrong passwords, disabled accounts, and missing authorities.
- Do not use `@WithMockUser` in place of real password tests.
- Verify 401 from authentication failures and 403 from authorization/CSRF failures for the right reasons.
- Measure verification performance and CPU/RAM usage, especially after raising the work factor.
- Have a controlled migration plan for legacy plaintext/NoOp/SHA-256 data.

## 16. Self-Check

**Question 1.** An application only needs to verify whether a newly entered password is correct. Should it store a password hash or an AES ciphertext?

**Question 2.** Why is SHA-256 a good hash function yet unsuitable on its own for storing passwords?

**Question 3.** Does a salt need to be secret? How does a pepper differ from a salt?

**Question 4.** Two users choose the same password. Why does BCrypt usually produce two different hashes?

**Question 5.** Why is `encoder.encode(raw).equals(stored)` not the right way to log in?

**Question 6.** Is `{bcrypt}` in `DelegatingPasswordEncoder` a key or an algorithm ID?

**Question 7.** If a system uses `DelegatingPasswordEncoder` and legacy hashes lack `{id}`, what should you check?

**Question 8.** If a user forgets their password, why not decrypt the hash to send it back?

**Question 9.** What does AES-GCM need to decrypt? Which component must be kept secret?

**Question 10.** Why is nonce reuse under the same key so dangerous with GCM?

**Question 11.** Why is a password KDF intentionally slow, yet an overly high cost still dangerous?

**Question 12.** Why does HTTP Basic's Base64 not protect passwords in transit?

**Question 13.** A database is leaked and contains secure bcrypt hashes. Is it completely impossible for passwords to be guessed?

**Question 14.** If encryption at rest is already enabled, do we still need to store password hashes at the application layer?

**Question 15.** Must a high-entropy random API token necessarily be handled identically to a human password?

**Question 16.** Does `PasswordEncoder.matches` returning true suffice to let a user read all data on the server?

**Suggested answers**

1. A one-way password KDF with an appropriate salt/cost; there is no need to decrypt old passwords.
2. Because it is too fast for offline password guessing by attackers.
3. Salts are not secret and are usually unique per hash; peppers are secret and kept outside the DB.
4. BCrypt generates a random salt on each encode call.
5. A new salt makes the hash string differ; use `matches` against the stored hash.
6. An algorithm ID used to choose the delegate, not a key.
7. Legacy hash format/algorithm, encoder mapping, and proper migration; do not disable verification.
8. Hashes have no decrypt API; use a password reset flow.
9. Key, nonce, and ciphertext/tag; the encryption key must remain secret.
10. Reusing a nonce with the same key can break confidentiality and integrity.
11. Slowness makes offline guessing costlier, but being too slow causes server load and DoS.
12. Base64 is trivially decoded; HTTPS/TLS is required.
13. No. Attackers can still test candidate guesses with the salt, just at higher cost.
14. Yes. Both mechanisms protect different security boundaries.
15. Not by default; the entropy and threat model of a token can differ from a human password.
16. No. Authorization (roles, permissions, owner, tenant) must still be enforced.

## 17. Official Documentation

- [Spring Security 6.5 – Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security – PasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [OWASP – Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP – Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- [OWASP – Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [Java SE 17 – JCA Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html)
- [NIST – Digital Identity Guidelines](https://pages.nist.gov/800-63-4/sp800-63b.html)
