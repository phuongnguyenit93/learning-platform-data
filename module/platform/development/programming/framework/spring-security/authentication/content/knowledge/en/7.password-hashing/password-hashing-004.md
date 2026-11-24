# BCryptPasswordEncoder and Input Limit Characteristics to Validate

> **Topic:** Spring Security → Authentication → **Password Hashing**. This lesson explains `BCryptPasswordEncoder`, how bcrypt stores and verifies passwords, the **72-byte limit on UTF-8 input**, the difference between bytes and Unicode characters, how to validate during registration, password changes, and login, work factor notes, hash formats, historical version bugs, and selecting alternative algorithms. Examples use **Java 17+ and Spring Security 6.5.11**, with a complete Gradle project, verifiable console output, and a Spring Security integration pattern.

## 1. Questions to Resolve

When implementing username/password authentication, developers often write:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String hash = encoder.encode(rawPassword);
boolean correct = encoder.matches(candidatePassword, hash);
```

The snippet above is an example inside a method that already has `rawPassword` and `candidatePassword` variables; it is not a standalone Java program. It states the two basic operations correctly, yet **does not describe the complete input policy**, especially for long or Unicode passwords.

Key questions:

1. How does BCrypt differ from plain SHA-256 or reversible encryption?
2. Why do two `encode` calls for the same password usually produce **two different hashes** while `matches` still returns true?
3. What does work factor (`strength`) mean, what is the default, and how should it be chosen?
4. What is **72 bytes** the limit of? Is it the same as `String.length() == 72`?
5. Can a user entering 25 three-byte Unicode characters hit the limit earlier than a user entering 72 ASCII characters?
6. If the frontend allows 100 characters while bcrypt only processes a prefix, what is the impact on password uniqueness?
7. What long-input validation bug affected a past Spring Security version, and why is applying patches necessary?
8. Should input validation live in registration, login, password reset, or `PasswordEncoder` itself?
9. When should you use `DelegatingPasswordEncoder` or another algorithm such as Argon2id?

**Guiding summary:** bcrypt is a salted password-hashing function with adjustable computational cost, but **bcrypt input has a byte limit**. Do not wait until `encode` or `matches` runs to decide your password policy. A secure application needs uniform rules across every path that handles passwords.

## 2. Where Does BCryptPasswordEncoder Live in Spring Security?

Spring Security provides the interface:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);

    boolean matches(CharSequence rawPassword, String encodedPassword);

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

This is a signature illustrating API semantics, not code to redeclare the interface in your project.

- `encode(raw)` transforms the original password into a **storable password hash**, not reversible encryption.
- `matches(raw, storedHash)` verifies the input password against the stored hash; **never** call `encode` on raw and compare two newly generated hash strings.
- `upgradeEncoding(storedHash)` can indicate that the current hash uses weaker parameters than desired and should be upgraded after a successful verification.

`BCryptPasswordEncoder` is the implementation in package:

```java
org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder
```

Typical username/password flow:

```text
HTTP POST login / HTTP Basic
    ↓
Authentication Filter → UsernamePasswordAuthenticationToken
    ↓
AuthenticationManager → DaoAuthenticationProvider
    ├─ UserDetailsService.loadUserByUsername(username)
    │     └─ getPassword() returns the password hash stored in DB
    └─ PasswordEncoder.matches(rawPassword, storedHash)
    ↓
Valid credentials + valid account → Authentication succeeds
Invalid credentials or blocked account → AuthenticationException
```

`UserDetailsService` typically only loads the username, hash, authorities, and user status; it does not check the password itself. `DaoAuthenticationProvider` uses `PasswordEncoder`. When a password is created or changed successfully, the application should enforce the **same encoding policy and input limits** as the login path.

Never store raw passwords; never expose passwords/hashes in responses, URLs, metrics, or logs. Password hashes remain sensitive data because they are exposed to offline password-guessing attacks if the DB is leaked.

## 3. How Does BCrypt Work?

BCrypt relies on an algorithm with scalable computational cost; each hash normally uses a **16-byte (128-bit) random salt**. The salt is encoded **inside the hash string**, ensuring two accounts with the same password do not automatically share the same hash, and rendering precomputed hash lookup tables ineffective.

A standard BCrypt hash uses the modular crypt format:

```text
$2a$10$<22 salt characters><31 hash characters>
│   │  └──────── salt and hash result encoded per bcrypt
│   └─────────── cost / log-rounds
└─────────────── bcrypt version ($2a, $2b, $2y...)
```

The line above uses descriptive notation, not a real hash to store. With modern bcrypt:

- The direct string from `BCryptPasswordEncoder` is typically **60 ASCII characters** long.
- `$2a$`, `$2b$`, `$2y$` are version labels supported by the encoder. The default for `new BCryptPasswordEncoder()` in Spring Security 6.5 is `$2a$`.
- `10` is the default cost. This is a logarithmic parameter where work grows roughly as `2^cost`; raising it from 10 to 11 roughly doubles the hash computation work, not a 10% increase.
- Salt is already embedded in the encoded hash; there is **no need** for an extra salt column just for bcrypt to work.
- The stored field must be long enough: direct BCrypt is typically 60 characters; `DelegatingPasswordEncoder` prepends `{bcrypt}`; when supporting algorithm upgrades, design a wider column such as `VARCHAR(255)` or per your project's encoder requirements.

Example:

```java
BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(10);

String a = encoder.encode("demo-passphrase-123");
String b = encoder.encode("demo-passphrase-123");

boolean okA = encoder.matches("demo-passphrase-123", a);
boolean okB = encoder.matches("demo-passphrase-123", b);
```

The snippet above is illustrative, yet the crucial behavior is that both `okA` and `okB` are `true`. Two `encode` calls usually use different salts, so `a` and `b` differ; **never use `a.equals(b)` to verify a password**. With random salts, never assume a deterministic hash output for a password.

### BCrypt vs. Plain SHA-256

```text
WRONG for password storage:
stored = SHA256(password)

RIGHT direction for password hashing:
stored = BCrypt(password, random salt, tuned cost)
login: BCrypt.verify(candidate, stored)
```

Plain SHA-256 is a fast hash useful for other purposes, yet **unsuitable as a standalone password-storage hash** because it allows guessing at high speed. BCrypt is intentionally designed to be slow to raise offline brute-force costs. BCrypt **is not encryption** and has no decrypt operation to recover the original password; if forgotten, execute a verified reset flow rather than "decoding the hash".

## 4. Most Important Limit: **72 Bytes**, Not 72 Characters

Traditional BCrypt supports at most **72 input bytes** for password data; many historical implementations silently processed only the first 72 bytes. In patched Spring Security versions, generating a new bcrypt hash with input exceeding 72 bytes is rejected by the underlying library; applications should still **proactively validate upfront** to provide clear messages and protect all entry paths uniformly.

The OWASP Password Storage Cheat Sheet recommends capping bcrypt passwords at **72 bytes or fewer if the actual implementation has a tighter limit**.

### 4.1. Three Kinds of Length Not to Confuse

| Measurement | Java Example | Meaning |
| --- | --- | --- |
| UTF-16 code units | `password.length()` | Length of `String`, **not bytes** |
| Unicode code points | `password.codePointCount(0, password.length())` | Number of code points, not visible user characters |
| **UTF-8 bytes** | `password.getBytes(StandardCharsets.UTF_8).length` | **The unit that must be checked for bcrypt** |

The number of graphemes visible to a user can also differ from the code point count: accented characters may combine multiple code points, and emojis may join multiple code points together. Never take `maxlength="72"` in HTML as proof that the server enforces a 72-byte limit.

Illustrative table in UTF-8:

| Password value (illustrative) | Java `String.length()` | UTF-8 bytes | Status under 72-byte limit |
| --- | ---: | ---: | --- |
| `"A".repeat(72)` | 72 | 72 | At exact limit |
| `"A".repeat(73)` | 73 | 73 | Exceeds |
| `"é"` (U+00E9, precomposed) | 1 | 2 | Valid size |
| `"e\u0301"` (e + combining mark) | 2 | 3 | Valid size |
| `"界".repeat(24)` | 24 | 72 | At exact limit |
| `"界".repeat(25)` | 25 | 75 | Exceeds |
| `"😀".repeat(18)` | 36 | 72 | At exact limit |
| `"😀".repeat(19)` | 38 | 76 | Exceeds |

One emoji `😀` typically takes **4 UTF-8 bytes** and **2 UTF-16 code units**. One CJK character `界` takes **3 UTF-8 bytes**. Thus two passwords that both look like "25 characters" can have vastly different byte lengths.

### 4.2. Why Is Exceeding 72 Bytes a Security Issue?

In some older bcrypt implementations, bytes past the cutoff **do not contribute to distinguishing passwords during verification**. In that case, two inputs sharing the same 72-byte prefix with different suffixes may be treated as identical. This misleads users into thinking their password is longer and stronger than it actually is.

Conceptual example:

```text
input #1 = <same first 72 bytes> + "X"
input #2 = <same first 72 bytes> + "Y"

In a silently truncating implementation:
      bcrypt(input #1) and bcrypt(input #2)
      may depend solely on the shared prefix.
```

This is a **risk model of an implementation without length validation**, not a description of allowed behavior in patched Spring Security 6.5.11. Do not use this example to attempt unauthorized access to anyone's account.

**Never call `substring(0,72)` or `Arrays.copyOf(...,72)`** to "fix" input before hashing/matching. Truncating a password alters the user-chosen secret; two distinct passwords can collapse into the same hash. The right rule is to **reject overlong input before hashing**, or choose an algorithm supporting the length required by the product.

### 4.3. CVE-2025-22228 and Version Limits

Spring published **CVE-2025-22228** regarding `BCryptPasswordEncoder.matches(...)` erroneously accepting certain passwords exceeding the limit when they shared the same prefix. Affected Spring Security branches were fixed in releases such as **6.4.4, 6.3.8** (and corresponding fixes on older branches). Official advisory: https://spring.io/security/cve-2025-22228/.

**Actionable steps:** upgrade the library to a patched release of your branch or a newer supported release, inspect your dependency tree and transitive dependencies, and write tests for overlong input cases. Frontend-only limits never replace library patches or server-side policies.

Spring Security **6.5.11** in this example is a version after the cited patches; when using another version, read the advisory/changelog and test that exact implementation. Do not assume **all bcrypt libraries** throw the same exception type on `encode` or return the same status on `matches`: implementation differences are precisely why limits must be enforced at your application boundary.

## 5. Password Validation Rules: Apply on Both **Write** and **Verify**

### 5.1. Paths That Must Share a Common Policy

- **Account registration:** validate the password before calling `PasswordEncoder.encode(...)`, then save the hash, never raw.
- **Logged-in password change:** verify the current password through a trusted mechanism; validate the new password before encoding; update the hash inside a transaction.
- **Forgot password:** verify recovery proof first; validate the new password before encoding; revoke recovery tokens/sessions per policy.
- **Login:** validate input according to the active encoder's policy; never silently drop trailing bytes or downgrade to a weaker algorithm when encountering overlong input.
- **Admin user import or creation:** must also follow the policy if a user/administrator sets a password.
- **Other APIs calling the password encoder directly:** avoid side paths that bypass controller validation.

### 5.2. Why Must Validation Happen on the Backend?

The frontend can validate for fast UX, yet users/API clients can bypass the frontend. Therefore, **backend validation** must be the authoritative source of truth. Do not treat `@Size(max=72)` on a Java `String` as sufficient because Bean Validation counts **character units**, not UTF-8 bytes.

A minimal suitable rule set for bcrypt:

```text
rawPassword is not null
rawPassword is not empty
Valid UTF-8 encoding (no malformed surrogates)
UTF-8 byteLength <= 72
No automatic trimming, lowercasing, truncation, or arbitrary Unicode normalization
Other rules (minimum length, blocklist, breached passwords...) applied separately
```

For extremely large inputs, block them at the gateway/request-size limit and application layer **before running CPU-intensive password hashing**, mitigating denial-of-service risks. `BCryptPasswordEncoder` also incurs CPU cost on every password check; rate limiting and authentication monitoring are essential.

### 5.3. Do Not Arbitrarily Normalize Passwords

Two visually identical strings can have different bytes:

```text
U+00E9       : "é"                 → UTF-8 2 bytes
U+0065 U+0301: "e" + acute accent  → UTF-8 3 bytes
```

A chosen password is a **secret string**, not a search field that needs diacritics stripped. If the application intentionally uses Unicode normalization such as NFC under an approved policy, apply it consistently at **every** point where passwords are set, checked, or changed, with a migration plan for old passwords; never change it silently once hashes exist, or users may be unable to log in.

**Do not trim whitespace, do not auto-lowercase, do not strip diacritics, and do not substitute control characters.** Not only does that break valid passwords, it can also introduce collisions via unintended transformations.

## 6. Runnable Java 17+: Checking 72 UTF-8 Bytes and BCryptPasswordEncoder

The demo below is a Java program run from Gradle. It uses **Spring Security Crypto 6.5.11** via the Spring Security Core dependency, hashes passwords with `BCryptPasswordEncoder(10)`, and wraps the encoder with an input-validation policy enforced in both `encode` and `matches`.

The examples only print **lengths and boolean results**, never full hashes, personal passwords, or secrets. All passwords in code are test fixtures.

### 6.1. Structure

```text
bcrypt-input-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/BCryptInputDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'bcrypt-input-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

application {
    mainClass = 'demo.BCryptInputDemo'
}
```

### 6.2. Complete Program

Create `src/main/java/demo/BCryptInputDemo.java`:

```java
package demo;

import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class BCryptInputDemo {
    private static final int MAX_BCRYPT_UTF8_BYTES = 72;

    public static void main(String[] args) {
        PasswordEncoder encoder = new ValidatedBcryptEncoder(10);

        String password = "demo-passphrase-123";
        String hash = encoder.encode(password);

        // Do not print the full hash or real password.
        System.out.println("prefix=" + hash.substring(0, 7));
        System.out.println("hashLength=" + hash.length());
        System.out.println("matchCorrect="
                + encoder.matches(password, hash));
        System.out.println("matchWrong="
                + encoder.matches("wrong-password", hash));

        String ascii72 = "A".repeat(72);
        String ascii73 = "A".repeat(73);
        String unicode24 = "界".repeat(24);
        String unicode25 = "界".repeat(25);

        System.out.println("ascii72Bytes=" + utf8BytesForDisplay(ascii72));
        System.out.println("ascii73Bytes=" + utf8BytesForDisplay(ascii73));
        System.out.println("unicode24Bytes="
                + utf8BytesForDisplay(unicode24));
        System.out.println("unicode25Bytes="
                + utf8BytesForDisplay(unicode25));

        System.out.println("encodeAscii72="
                + acceptedByEncode(encoder, ascii72));
        System.out.println("encodeAscii73="
                + acceptedByEncode(encoder, ascii73));
        System.out.println("encodeUnicode24="
                + acceptedByEncode(encoder, unicode24));
        System.out.println("encodeUnicode25="
                + acceptedByEncode(encoder, unicode25));

        // Policy is wrapped in PasswordEncoder so it applies to login as well.
        System.out.println("overlongLogin="
                + encoder.matches(ascii73, hash));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("accentBytes="
                + utf8BytesForDisplay(composed) + "/"
                + utf8BytesForDisplay(decomposed));
    }

    // Only used to measure bytes for literal tests; do not log real password lengths.
    private static int utf8BytesForDisplay(String input) {
        return input.getBytes(StandardCharsets.UTF_8).length;
    }

    private static boolean acceptedByEncode(
            PasswordEncoder encoder, String input) {
        try {
            encoder.encode(input);
            return true;
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    // A validation policy invoked for both registration and login.
    private static void checkBcryptInput(CharSequence rawPassword) {
        if (rawPassword == null) {
            throw new IllegalArgumentException("Password is required");
        }

        String input = rawPassword.toString();

        if (input.isEmpty()) {
            throw new IllegalArgumentException("Password is empty");
        }

        // Any valid UTF-16 string with >72 code units definitely exceeds
        // >72 UTF-8 bytes. Reject early to avoid large allocations.
        if (input.length() > MAX_BCRYPT_UTF8_BYTES) {
            throw new IllegalArgumentException(
                    "Password exceeds bcrypt UTF-8 byte limit");
        }

        try {
            int bytes = StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(input))
                    .remaining();

            if (bytes > MAX_BCRYPT_UTF8_BYTES) {
                throw new IllegalArgumentException(
                        "Password exceeds bcrypt UTF-8 byte limit");
            }
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException(
                    "Password contains invalid Unicode", ex);
        }
    }

    // Wrapper keeps rules consistent right inside PasswordEncoder.
    private static final class ValidatedBcryptEncoder
            implements PasswordEncoder {
        private final BCryptPasswordEncoder delegate;

        private ValidatedBcryptEncoder(int strength) {
            this.delegate = new BCryptPasswordEncoder(strength);
        }

        @Override
        public String encode(CharSequence rawPassword) {
            checkBcryptInput(rawPassword);
            return delegate.encode(rawPassword);
        }

        @Override
        public boolean matches(
                CharSequence rawPassword, String encodedPassword) {
            try {
                checkBcryptInput(rawPassword);
            } catch (IllegalArgumentException ex) {
                // During login: reject invalid credentials;
                // do not let exceptions leak details into the response.
                return false;
            }
            return delegate.matches(rawPassword, encodedPassword);
        }

        @Override
        public boolean upgradeEncoding(String encodedPassword) {
            return delegate.upgradeEncoding(encodedPassword);
        }
    }
}
```

Run inside `bcrypt-input-demo` with a JDK 17-compatible Gradle:

```bash
gradle run
```

If the project has a Gradle Wrapper, use `./gradlew run` (macOS/Linux) or `gradlew.bat run` (Windows). The program's stdout (excluding Gradle logs):

```text
prefix=$2a$10$
hashLength=60
matchCorrect=true
matchWrong=false
ascii72Bytes=72
ascii73Bytes=73
unicode24Bytes=72
unicode25Bytes=75
encodeAscii72=true
encodeAscii73=false
encodeUnicode24=true
encodeUnicode25=false
overlongLogin=false
accentBytes=2/3
```

**Why are these lines reliable?**

1. `new BCryptPasswordEncoder(10)` in the 6.5 line produces the default hash format prefixed with `$2a$10$` and a total direct length of 60 characters. The trailing salt and hash are randomized, so **never print or commit fixed hash strings**.
2. `matches` uses the salt/cost embedded in the hash, so the right password returns `true` and a wrong password returns `false`.
3. ASCII `"A"` is one UTF-8 byte, so 72 A's are exactly 72 bytes; 73 A's exceed the limit.
4. `界` is three UTF-8 bytes; 24 characters are 72 bytes, while 25 characters are 75 bytes.
5. `ValidatedBcryptEncoder` rejects before any encode/matches path if the limit is exceeded. Hence `overlongLogin=false` is **behavior guaranteed by the program's wrapper**, independent of how a particular internal bcrypt release handles long passwords.
6. The two ways of writing `é` look alike yet measure 2 and 3 bytes, so Unicode limits cannot be checked solely by visible character counts.
7. `checkBcryptInput` uses `CharsetEncoder` with `CodingErrorAction.REPORT` to reject invalid UTF-16 Unicode rather than silently replacing characters during encoding.
8. `acceptedByEncode` uses test literals and catches exceptions deliberately; production code should map failures into clear validation messages, **never relying on raw dependency exception text exposed directly to clients**.

**Limitations of the demo:** this is a **minimal length-validation policy**, not a complete registration/login service. It does not include breached-password screening, rate limiting, DB persistence, MFA, account lockouts, sessions, or transactions. Those responsibilities must be added in a real application.

### 6.3. Why Check `input.length() > 72` First?

A valid `String` has a UTF-8 byte count **at least equal to its number of UTF-16 code units** (ASCII: 1 byte per unit; non-ASCII characters typically take more bytes). Thus if `String.length() > 72`, the password is guaranteed to exceed 72 bytes.

This is a **pre-filter to reduce allocations on huge inputs**, while the **final decision must still rely on UTF-8 byte length**. Never reverse this reasoning: a `String` of 25 code units can still be 75 bytes long.

Also enforce a request-body limit at the HTTP layer to block oversized inputs before converting them into a `String` and before invoking password hashing. Controlling the relationship between password length, memory, and CPU is an operational safety issue, not merely UX.

## 7. Integrating into Spring Boot: PasswordEncoder Must Be a Shared Policy

Some projects only check limits in the `POST /register` controller while skipping other paths: HTTP Basic, form login, admin APIs, and password reset. As a result, input handling and verification can become **inconsistent**.

One solution is registering a `PasswordEncoder` bean wrapped with the validator:

```java
@Configuration
class PasswordConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new ValidatingPasswordEncoder(
                new BCryptPasswordEncoder(12));
    }
}
```

This is a **configuration snippet**, assuming `ValidatingPasswordEncoder` exists and applies logic like `ValidatedBcryptEncoder` in section 6. It is not a complete Java file. `12` is merely an **example parameter**, not a universally recommended default cost for every environment. Benchmark on real hardware before choosing.

If using `DaoAuthenticationProvider` and one consistent `PasswordEncoder` bean, the provider calls `matches(...)` on that encoder to verify passwords. Registration/password-change controllers call `encode(...)` on the same encoder. A guard at the encoder lowers the risk of missing validation across entry points — though you should still validate earlier in the request/service layer to return helpful errors and avoid invoking BCrypt needlessly.

### When Using DelegatingPasswordEncoder

Spring Security typically recommends `PasswordEncoderFactories.createDelegatingPasswordEncoder()` to support multiple algorithms/hash versions via prefixes:

```text
Direct bcrypt hash:
$2a$10$...

DelegatingPasswordEncoder hash:
{bcrypt}$2a$10$...
```

`DelegatingPasswordEncoder` reads `{id}` to pick the matching encoder; it supports migrating from old hashes and changing algorithms in the future. If you wrap the **entire** `DelegatingPasswordEncoder` with a rigid 72-byte policy, that could also reject valid long passwords stored under Argon2id/scrypt. Therefore:

- If **all new hashes are bcrypt** and the uniform policy is 72 bytes, applying the 72-byte validator across all password paths makes sense.
- If the system runs **multiple algorithms concurrently**, the validation policy must account for the **algorithm of the hash being verified** and the algorithm used for **new passwords**, without opening a downgrade path or making UX confusing.
- If you want to support passphrases longer than 72 bytes in the future, **pick an appropriate algorithm before rolling out the new password policy**; do not merely raise a `maxlength` while keeping BCrypt.
- For legacy hashes lacking `{id}`, an explicit migration is needed; the default `DelegatingPasswordEncoder` may throw due to an unmapped id. Never blindly prepend `{bcrypt}` to every row without verifying the actual algorithm.

**Never use `NoOpPasswordEncoder`** to bypass input errors; doing so stores plaintext passwords in the DB and introduces severe risk. Never use a plain SHA-256 encoder as a "faster" fallback path for long passwords.

## 8. Why Should You Never Arbitrarily Truncate or Pre-Hash?

### 8.1. Truncation Alters the Secret

A common anti-pattern:

```java
// DO NOT DO THIS: truncating password to fit "72 characters".
String shortened = rawPassword.substring(
        0, Math.min(rawPassword.length(), 72));
String encoded = encoder.encode(shortened);
```

The snippet above is also wrong because it counts **Java characters**, not UTF-8 bytes. Carelessly slicing a string containing a surrogate pair can also produce malformed Unicode.

The more serious consequence: the user thinks they set password `secret...A`, while the system stores the hash of a shorter prefix. Depending on implementation, verifying a different string with the same prefix could succeed. **Reject overlong input**, never shorten it in the backend.

### 8.2. Pre-Hashing Is Not a Free Fix

Some resources mention hashing the password with SHA-256/SHA-512 first and passing the digest into bcrypt. That idea carries risks:

- Hash bytes can contain **NUL** for bcrypt implementations that treat input as NUL-terminated strings.
- If encoding the digest as Base64/Hex, its length must still fit bcrypt's limit and requires versioning.
- If using an **unsalted/unkeyed** inner hash and that hash leaks from another system, **password shucking** can make offline attacks more effective than expected.
- Changing the pipeline from `bcrypt(password)` → `bcrypt(SHA256(password))` is **incompatible with old hashes** without a migration plan.

OWASP discusses using **HMAC with a separately protected pepper** before bcrypt when pre-hashing is genuinely required; that is an additional security design, not a copy-paste blog trick. If a new application wants long passwords, **Argon2id should be evaluated first** rather than inventing a custom BCrypt variant.

### 8.3. Do Not Automatically Normalize/Trim

`encode` and `matches` must apply the exact same string handling. Never normalize passwords on login while forgetting registration or vice versa. Never print password hashes or normalized password variants to logs for debugging.

## 9. Work Factor, Performance, and DoS Risk

`BCryptPasswordEncoder` uses `strength` — the work factor parameter. In Spring Security 6.5:

- `new BCryptPasswordEncoder()` defaults to cost **10**.
- `new BCryptPasswordEncoder(int strength)` accepts costs from **4 to 31**.
- Overloads exist specifying `BCryptVersion`, `SecureRandom`, and cost.
- Cost is stored inside the encoded hash. When switching the encoder to a new cost, old hashes remain verifiable using the parameter embedded in the hash.
- `upgradeEncoding(encodedHash)` can return true if the stored cost is lower than the current encoder's cost; **rehashing must only occur after verifying the right password** and with a process to persist the updated hash.

### 9.1. How to Choose Cost

Do not mechanically pin every application to cost 10 or 16. Each +1 cost increment roughly doubles the work; actual elapsed time depends on CPU, runtime, request concurrency, and system load. Per Spring Security documentation, measure and tune toward a verification duration suited to operational requirements (the docs cite roughly one second as a reference benchmark).

Measure with controlled benchmarks:

1. Pick machines/nodes and concurrent load representative of production.
2. Measure median/p95/p99 latency of `matches(...)` for realistic password lengths.
3. Inspect CPU, memory, request queues, and login throughput under concurrent load.
4. Pick a cost slow enough to deter offline guessing without exhausting system resources during login spikes.
5. Configure rate limits, login throttling, and monitoring; never rely on an excessively high cost to replace credential-stuffing defenses.

**Never document verification latency as a fixed constant**: a cost-12 hash does not take a fixed number of milliseconds across all hardware.

### 9.2. Long Passwords and High Cost Are Two Separate Issues

The 72-byte limit addresses **bcrypt input semantics**. Rate limiting and cost tuning address **CPU expenditure per verification**. A system blocking passwords >72 bytes can still be overloaded by excessive login attempts with short passwords. Conversely, a system with rate limiting that silently truncates passwords still suffers a credential-integrity flaw.

## 10. Legacy System Compatibility and Migration Planning

When millions of bcrypt hashes already live in the DB, assess the **algorithm, library versions, and validation history** before changing policies:

### 10.1. Inventory

- Review encoder configuration, dependency versions, and how the app actually calls `encode/matches`.
- Check stored hash formats (`$2a$...`, `{bcrypt}$2a$...`, other prefixes) and costs used.
- Check whether the old app allowed passwords >72 bytes; did frontend `maxlength` check bytes or only characters?
- Check whether the old library truncated or erroneously accepted long passwords.
- Never log or export the hash table for analysis outside secure boundaries; analyze configuration and code first.

### 10.2. Original Passwords Cannot Be Recovered from Hashes

Because password hashing is one-way, the system cannot inspect a hash to tell how many bytes or which bytes past byte 72 the user originally entered. If there is risk that old hashes were created from overlong/truncated passwords:

1. Prioritize applying the patch and stopping new invalid credentials from being created.
2. Plan **forced password changes** or proof-verified recovery for the affected cohort based on risk level.
3. Never mark an old hash as "migrated to Argon2id" simply by editing its prefix.
4. Once a user presents a valid right password, upgrade the hash via verify-then-rehash with the new algorithm; maintain versioned policies and storage.
5. Revoke sessions/tokens if incident policy requires it; updating a password in the DB does not automatically invalidate existing JWTs immediately.

Some users may have entered long passwords on an older library version and can no longer log in the same way after patching. You need a **clear, secure recovery procedure**, never temporarily re-enabling a vulnerable library version to "fix a UX issue".

### 10.3. Using DelegatingPasswordEncoder for Gradual Transitions

A system with multiple encoded-password formats should typically use `DelegatingPasswordEncoder` because it maps `{id}` to specific encoders. When adjusting algorithms:

- Old hashes continue using their corresponding encoder for verification.
- New hashes use the chosen `idForEncode` algorithm.
- After successful verification, the application can persist a new hash if `upgradeEncoding`/migration policy calls for it.
- Password validation must consider the algorithmic limits of both old and new hashes without breaking valid logins or creating a downgrade path.

However, if a user already has a bcrypt hash generated from a password exceeding 72 bytes due to legacy truncation, there is no way to recover the full password from the hash. Recovery may still be necessary.

## 11. Mandatory Test Cases

Your test suite should verify **byte limits and actual authentication paths**, not merely a character-counting helper.

| Case | Input | Result to Guarantee |
| --- | --- | --- |
| ASCII at exact limit | 72 `A` characters | Accepted if passing other rules |
| ASCII over limit | 73 `A` characters | Rejected when setting password and on login |
| 3-byte Unicode at limit | 24 `界` characters | 72 bytes, valid within limit |
| 3-byte Unicode over limit | 25 `界` characters | 75 bytes, rejected |
| 4-byte emoji at limit | 18 `😀` characters | 72 bytes |
| Emoji over limit | 19 `😀` characters | 76 bytes, rejected |
| Precomposed vs. combining accent | `é` vs `e + combining mark` | Not treated as identical unless a normalization policy exists |
| Invalid UTF-16 surrogate | Lone high surrogate | Rejected, not silently replaced with `?` |
| Empty/null password | `""`, `null` | Rejected before BCrypt |
| Correct password | Stored hash | `matches` returns true |
| Wrong password | Different string | `matches` returns false |
| Input >72 with shared prefix | Different suffix after 72 bytes | Must not be accepted as the same password |
| Two `encode` calls for same raw | Same raw, random salt | Each hash verifies; never compare new hashes with `equals` |
| Malformed hash | Non-bcrypt string | Login fails safely; no plaintext fallback |
| Old BCrypt cost | Hash with lower work factor | Verifies, may signal `upgradeEncoding` |
| Password reset | New raw password | Validator and encoder invoked before saving |
| HTTP Basic/form login | Overlong raw password | Backend rejects, not only frontend |
| Legacy hash and delegating prefix | `{bcrypt}` or old format | Verification/migration follows versioned policy |

### 11.1. Unit Tests for Boundaries

The JUnit 5 snippet below **depends on extracting the validator/wrapper class into a dedicated production class**. It is not a standalone test without package/imports/project setup:

```java
@Test
void bcryptInputLimitMustBeCheckedInUtf8Bytes() {
    PasswordEncoder encoder = new ValidatedBcryptEncoder(10);

    assertDoesNotThrow(() -> encoder.encode("A".repeat(72)));
    assertThrows(IllegalArgumentException.class,
            () -> encoder.encode("A".repeat(73)));

    assertDoesNotThrow(() -> encoder.encode("界".repeat(24)));
    assertThrows(IllegalArgumentException.class,
            () -> encoder.encode("界".repeat(25)));
}
```

In the demo project, `ValidatedBcryptEncoder` is a private nested class inside `BCryptInputDemo`; to write standalone tests, move it to its own file (e.g., `ValidatedBcryptEncoder.java`), keeping the validation logic and choosing appropriate visibility. When testing via `AuthenticationManager`/`DaoAuthenticationProvider`, verify that overlong input cannot authenticate successfully even when an existing hash shares the prefix. Controller tests that only check validation errors do not replace real login integration tests.

### 11.2. Testing with Real Spring Security

- Create an account with a valid hash; `DaoAuthenticationProvider` must accept the correct raw password and reject an incorrect one.
- HTTP Basic/form login with a password >72 bytes must fail to produce a successful `Authentication`.
- Password reset uses the same validator and saves nothing when validation fails.
- If using `DelegatingPasswordEncoder`, test valid prefixes and unsupported id cases.
- Against patched and historical libraries in a controlled test environment, test the CVE scenario to confirm the patch is active. Never deploy a vulnerable version in production.
- At the DB layer, confirm the password column does not truncate encoded hashes. Direct bcrypt hashes and `{bcrypt}`-prefixed hashes have different lengths.
- Test NFC/NFD Unicode and surrogates to ensure consistent policy handling.
- Test concurrent logins to measure latency/CPU; do not mistake a unit test for a load test.

## 12. Common Mistakes

1. **Using `password.length() <= 72` as the sole check.** Fails on multi-byte Unicode; UTF-8 bytes are required.
2. **Putting `maxlength=72` only on the frontend.** Easily bypassed by API clients, and maxlength typically does not count bytes.
3. **Truncating passwords to 72 characters or bytes.** Discards part of the user's secret, allowing distinct passwords to collide.
4. **Assuming every Spring Security version handles long passwords identically.** CVE-2025-22228 existed historically; run patched versions and test behavior.
5. **Skipping checks on the login path.** Validating registration while letting a legacy provider process unexpectedly long inputs.
6. **Assuming a BCrypt hash is decryptable encryption.** Passwords must be reset, never recovered from hashes.
7. **Comparing two `encode(raw)` strings.** Random salts yield different hashes; use `matches(raw, hash)`.
8. **Storing passwords in plaintext, reversible encryption, or plain SHA-256.** Fails to provide desired offline attack resistance.
9. **Adding an external salt manually without understanding the format.** BCrypt already manages salt; custom formats complicate migration.
10. **Hardcoding salt or using a fixed-seed RNG.** Loses randomness; rely on default secure random generation.
11. **Choosing cost too low or too high without benchmarking.** Low cost is weak offline; excessive cost can stall logins.
12. **Forgetting rate limiting because BCrypt feels slow enough.** Online abuse can still exhaust resources.
13. **Using BCrypt and raising `maxlength` to 200 to encourage long passphrases.** Supporting >72 UTF-8 bytes requires choosing an appropriate algorithm.
14. **Using `substring` on Unicode and leaving lone surrogates.** Causes data loss/encoding mismatches.
15. **Silently trimming or normalizing passwords.** Breaks consistent verification against stored hashes.
16. **Forgetting to update CVE-affected dependencies.** UI validation alone does not fix known library behavior.
17. **Using `NoOpPasswordEncoder` as a workaround.** Results in plaintext password storage, which is unacceptable.
18. **Solving long inputs with ad-hoc SHA-256 pre-hashing.** Can introduce password shucking, NUL byte, and migration issues.
19. **Blocking all >72 passwords globally in a multi-algorithm app.** Accidentally rejects valid passwords under Argon2id/scrypt; tailor policy per active encoder.
20. **Catching BCrypt exceptions and returning raw internal messages to clients.** Return a clean validation error; avoid leaking unnecessary details.
21. **Having no Unicode tests.** ASCII-only tests miss byte-limit bugs.
22. **Keeping cost 10 forever without re-evaluation.** Hardware and risk evolve; plan controlled benchmarking and upgrades.
23. **Assuming `upgradeEncoding` saves the new hash automatically.** It is only a signal; a post-verify flow and transaction are needed to store the new hash.
24. **Logging hashes or passwords to debug login.** Can leak credentials and sensitive data; audit minimally with redaction.

## 13. Practice Exercises

**Exercise A — 72 bytes vs. 72 characters.** For `"x".repeat(72)`, `"界".repeat(24)`, `"😀".repeat(18)`, and `"界".repeat(25)`, compute UTF-16 code units, Unicode code points, and UTF-8 bytes. Explain why two strings with different character counts hit bcrypt's limit together.

**Exercise B — Write a validator.** Implement `checkBcryptInput(CharSequence)` as in section 6; add tests for empty, null, 72/73 ASCII bytes, 72/75 Unicode bytes, emoji, and a malformed surrogate. Never use `String.length()` as sufficient permission.

**Exercise C — Integrate into DaoAuthenticationProvider.** Define a `PasswordEncoder` bean wrapping the validator, configure `UserDetailsService`, and perform a real login with a test account. Send an overlong password via HTTP Basic/form login and verify authentication is rejected.

**Exercise D — Two different hashes.** Call `encode` twice for the same valid passphrase. Explain where the salt is stored, why hashes vary, and why `matches` still returns true.

**Exercise E — Cost.** In a test environment, benchmark cost 10/11/12 under representative concurrency, recording median/p95 and CPU. Pick a cost based on measurements and operational requirements; never copy an imaginary millisecond number from docs.

**Exercise F — Upgrading.** Given a DB containing low-cost `$2a$...` hashes and `{bcrypt}$2a$...` hashes, draft a gradual migration plan to `DelegatingPasswordEncoder`, defining prefix-parsing rules and post-verification rehashing.

**Exercise G — CVE inventory.** From the dependency tree, identify the `spring-security-crypto` version and corresponding patch. Write an integration test proving long passwords sharing a prefix are not falsely accepted. Never run an affected version in production.

**Exercise H — Long-password policy.** A product wants to support UTF-8 passphrases longer than 72 bytes. Propose an architecture using Argon2id, versioned password hash columns, migration rules, and tests; explain why raising a frontend limit alone is not enough.

### Completion Criteria

Learners can explain:

- How BCrypt uses salt and work factor, what format it stores directly, and how `matches` works.
- Why bcrypt's limit is **72 UTF-8 bytes**, not 72 characters.
- How to safely validate ASCII, multi-byte Unicode, emoji, and malformed UTF-16.
- Why passwords must never be truncated and how CVE-2025-22228 relates to it.
- Where validation belongs so registration, login, and password change/reset paths stay consistent.
- When `DelegatingPasswordEncoder`, `upgradeEncoding`, or migrating to Argon2id is needed.
- How to test performance and migrations without causing login DoS or locking out legitimate accounts.

## 14. Primary Sources and References

- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): BCryptPasswordEncoder, cost, DelegatingPasswordEncoder, and migration.
- [Spring Security 6.5 — BCryptPasswordEncoder API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html): constructors, version, strength, `encode`, `matches`, and `upgradeEncoding`.
- [Spring Security 6.5 — Crypto Module](https://docs.spring.io/spring-security/reference/6.5/features/integrations/cryptography.html): 16-byte salt and work factor parameters.
- [Spring Security — CVE-2025-22228](https://spring.io/security/cve-2025-22228/): official advisory on validating passwords exceeding the length limit; affected branches and patches.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): bcrypt 72-byte input limit, pre-hashing/password shucking risks, and Argon2id guidance.
- [Spring Security — DelegatingPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html#_delegatingpasswordencoder): `{id}` prefix, supporting multiple hash formats.
- [Java 17 — CharsetEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html): `CodingErrorAction.REPORT` for invalid Unicode.

**Note:** runnable code targets Spring Security 6.5.11. For Spring Security 7, vendor-patched builds, or custom encoders, check Javadocs, advisories, and test byte-length handling on the exact deployed implementation. The goal is **building a clear, safe input policy**, not relying on an exception message or historical truncation behavior of a library.