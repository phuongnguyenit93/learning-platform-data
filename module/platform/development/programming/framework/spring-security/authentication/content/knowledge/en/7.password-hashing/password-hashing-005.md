# Pbkdf2PasswordEncoder and Algorithm Parameters

## 1. What Problem Does PBKDF2 Solve?

When a person registers an account or changes a password, the system must not store the original password string in the database. If the users table is leaked, plaintext passwords let attackers reuse them immediately. Computing only a fast hash such as `SHA-256(password)` is also insufficient: an attacker can test a huge number of guessed passwords in a short time.

**PBKDF2** (*Password-Based Key Derivation Function 2*) is a password-based key derivation function built on a pseudorandom function, typically **HMAC**. It deliberately performs many processing rounds so that **each password guess becomes more CPU-expensive**. Spring Security provides `org.springframework.security.crypto.password.Pbkdf2PasswordEncoder`, a `PasswordEncoder` implementation using PBKDF2 to generate and verify password storage data.

Conceptual inputs:

```text
rawPassword ─────────────────────────────┐
                                         │
unique random salt per encode call ──────┼── PBKDF2-HMAC
                                         │     (iterations, derived-key length)
additional secret if configured ─────────┘
                                                 │
                                                 v
                                     salt + derived key
                                                 │
                                         Hex or Base64
                                                 │
                                                 v
                                  encodedPassword in DB
```

**`encode(rawPassword)`** generates a new salt, derives the hash value, and returns a storable string. **`matches(rawPassword, storedEncodedPassword)`** extracts the salt information from the stored string, recomputes using the *exact same configuration*, and confirms the result. There is no "PBKDF2 decryption" operation to recover the password.

This lesson focuses on **`Pbkdf2PasswordEncoder` and algorithm parameters**: choosing HMAC, salt length, iterations, output length, optional secret, Hex/Base64, version presets, operating alongside `DelegatingPasswordEncoder`, and upgrading hashes without breaking logins.

## 2. Distinguishing Password Hashing from Reversible Encryption and Fast Hashing

| Technique | Example | Suitable for storing login passwords? | Why? |
| --- | --- | --- | --- |
| Storing directly | `password="Secret123!"` | **No** | Exposing the data table exposes the password. |
| Reversible encryption | AES with a decryption key | **Not the default choice** | If the key leaks, passwords can be decrypted in bulk. |
| Plain fast hashing | `SHA-256(password)`, MD5 | **No** | Lacks sufficient adaptive cost and risks precomputed lookup tables. |
| PBKDF2 with salt and proper iterations | PBKDF2-HMAC-SHA256 | **Yes**, when parameters, provider, and operations are chosen properly | Raises the cost of each password guess. |
| Memory-hard functions | Argon2id, scrypt | **Usually preferred for new systems when appropriate** | Beyond CPU, also adds memory cost, increasing difficulty for certain parallel attacks. |

PBKDF2 is an important option when an **algorithm ecosystem / FIPS infrastructure** must be satisfied. However, merely calling the Java PBKDF2 API **does not automatically make the entire application or JCA provider FIPS-certified**: certification also depends on the library, cryptographic module, deployment mode, and runtime environment.

Note: using HMAC-SHA256 *inside* PBKDF2 is **completely different** from storing a plain SHA-256 of the password. PBKDF2-HMAC-SHA256 iterates processing with a salt; plain fast hashing provides no comparable cost structure.

## 3. Algorithm Structure and Individual Parameters

In principle:

```text
PBKDF2(
    password = user password,
    salt = random bytes,
    iterations = iteration count,
    derivedKeyLength = derived key length,
    PRF = HMAC-SHA256 / HMAC-SHA512 / ...
)  --> derived key
```

With Spring Security's `Pbkdf2PasswordEncoder`, there is also an optional **secret**, plus an option to **encode the resulting string** in Hex or Base64. Key parameters:

| Parameter | Meaning | Unit/Note | Impact |
| --- | --- | --- | --- |
| `secret` | Server-side secret mixed into PBKDF2 input. | `CharSequence`; empty by default. | If the secret differs, old hashes can no longer verify under the new config. |
| `saltLength` | Length of random salt generated on each `encode`. | **Bytes**, not bits. | Independent salts ensure two records with the same password usually have different hashes. |
| `iterations` | Number of PBKDF2 rounds. | Positive integer; CPU cost scales with work factor. | Increasing iterations makes password guessing harder but also slows down login. |
| `SecretKeyFactoryAlgorithm` | PBKDF2-HMAC function to use. | For example `PBKDF2WithHmacSHA256`. | Must match when creating and verifying hashes. |
| `hashWidth` / derived key length | Output bit count of PBKDF2. | **Bits**, unlike `saltLength`. | 256 bits = 32 bytes; not the iteration count. |
| `encodeHashAsBase64` | Output string representation format. | Default `false`, meaning **Hex**. | Switching to Base64 changes the stored string and parsing. |

### 3.1. Salt Is Random and Can Be Public

Salt must be independent for each hash and generated from a secure random source. Salt is **not a second password**, need not be kept secret, and is stored alongside the hash result for later verification.

Example of two users both setting `Secret123!`:

```text
user A: saltA || PBKDF2("Secret123!", saltA, ...)
user B: saltB || PBKDF2("Secret123!", saltB, ...)
```

Normally `saltA != saltB`, so the stored values differ. This reduces the utility of rainbow tables and prevents directly inferring that two users share the same password from identical hashes. It **does not save** weak passwords from all attacks: an adversary with the hash and salt can still guess offline, paying the PBKDF2 cost per attempt.

In the `v5_8` preset, `saltLength=16` **bytes** (128 bits), not 16 Hex characters. Looking at Hex output, 16 bytes of salt occupy **32 Hex characters**.

### 3.2. Iterations Are Cost, Not Password Length

`iterations=310_000` means executing 310,000 algorithmic rounds, **not** hashing into 310,000 characters or taking a fixed number of milliseconds on every machine.

Increasing from 310,000 to 600,000 rounds typically increases verification cost roughly proportionally to the round count, though actual duration depends on the JDK/JCA provider, CPU, concurrent load, and deployment environment.

Do not set work factor solely by intuition that "a bigger number is safer": login endpoints flooded by attackers can exhaust CPU and cause denial of service. Benchmark **on production machines or an equivalent environment**, with concurrency limits, rate limiting, and an operational plan. Performance tests should measure percentiles and concurrent authentication, not just a single call on a laptop.

### 3.3. HMAC Algorithm and Output Length Are Distinct

The name `PBKDF2WithHmacSHA256` states that the **PRF is HMAC-SHA256**. It does not mean salt length is 256 bits or that a default iteration count is derived from that name. `SecretKeyFactoryAlgorithm` in `Pbkdf2PasswordEncoder` offers choices such as:

- `PBKDF2WithHmacSHA1`: mainly found in legacy data; discouraged for new systems.
- `PBKDF2WithHmacSHA256`: practical choice for modern PBKDF2.
- `PBKDF2WithHmacSHA512`: another option with its own iteration profile.

Output length is e.g. **256 bits = 32 bytes**. Even when changing the HMAC algorithm, changing output length or selecting a new profile must be managed as a hash version change because it can render `matches` incompatible with old records.

**Do not confuse terms:** PBKDF2 is a *key derivation function*; Spring Security uses it under the `PasswordEncoder` contract to store a **password verifier**, not to use the password hash directly as an AES key for general business purposes.

### 3.4. Additional Secret: Distinct from Salt

Constructors accept a `secret` parameter. Spring Security can incorporate the secret alongside the random salt as a server-side secret. When using a non-empty secret:

- The secret must come from a secret manager or secure configuration mechanism; **never hard-code** it into the repository.
- Never store the secret in the same DB hash record or return it over an API.
- If the secret is changed or lost, old hashes may stop verifying; manage secret versions and credential migration/reset.
- The secret does not replace passwords, salts, work factors, infrastructure key protection, or MFA.
- Do not assume every way of "adding pepper" is a compatible model; if your organization has a specific pepper/HSM policy, the design must adhere to that policy and be tested.

Spring Security's `defaultsForSpringSecurity_v5_8()` preset uses an **empty secret**. That is not a broken default configuration; an external pepper is an optional hardening measure depending on your risk model.

## 4. Concrete Preset Parameters in Spring Security 6.5.11

`Pbkdf2PasswordEncoder` provides convenient factory methods named after versions. A version suffix **does not mean** it only works in that framework version; it preserves hash configuration stability as the framework evolves.

| API preset | Salt | Iterations | PRF | Derived key | Notes |
| --- | ---: | ---: | --- | ---: | --- |
| `defaultsForSpringSecurity_v5_5()` | 8 bytes | 185,000 | HMAC-SHA1 | 256 bits | Legacy profile, deprecated in 6.5; kept to verify legacy data. |
| **`defaultsForSpringSecurity_v5_8()`** | **16 bytes** | **310,000** | **HMAC-SHA256** | **256 bits** | Recommended preset replacing the older preset in API 6.5. |
| Application-designed profile | e.g., 16 bytes | e.g., 600,000 | e.g., HMAC-SHA256 | e.g., 256 bits | Must assign a dedicated version ID, benchmark, and manage migration. |

These parameters correspond to **Spring Security 6.5.11** and should not be extrapolated to every era. Reference: [Pbkdf2PasswordEncoder API 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/Pbkdf2PasswordEncoder.html).

**Do not confuse framework defaults with recommended production work factors for all times.** The OWASP Password Storage Cheat Sheet currently cites **PBKDF2-HMAC-SHA256 at 600,000 iterations** where PBKDF2/FIPS is needed, higher than the `v5_8` preset's 310,000 rounds. This is why systems need their **own policy and versioning** rather than assuming every production app should merely call the preset with no further evaluation.

600,000 **is not a number guaranteeing an exact runtime**. Tune according to your threat model, latency target, concurrent logins, and hardware environment. When choosing higher iterations, retain the old configuration to verify previously created hash records.

## 5. Constructors, Algorithms, and Differences Between Hex/Base64

Quick way to create an encoder from the preset:

```java
Pbkdf2PasswordEncoder encoder =
        Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();
```

How to set an explicit profile using Spring Security 6.5's constructor:

```java
Pbkdf2PasswordEncoder tuned = new Pbkdf2PasswordEncoder(
        "", // empty server-side secret in this example
        16, // saltLength in bytes
        600_000,
        Pbkdf2PasswordEncoder.SecretKeyFactoryAlgorithm.PBKDF2WithHmacSHA256
);
```

The constructor taking `SecretKeyFactoryAlgorithm` is recommended over older constructors accepting `hashWidth` (which are deprecated). **Do not pick a deprecated constructor merely to pass an arbitrary output length** without understanding data compatibility.

How to switch representation to Base64:

```java
Pbkdf2PasswordEncoder base64Encoder =
        Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();
base64Encoder.setEncodeHashAsBase64(true);
```

Default is **Hex**. With the v5_8 preset:

- 16 bytes of salt + 32 bytes of derived key = **48 bytes** of binary data.
- Hex represents 48 bytes as **96 characters**.
- Base64 represents 48 bytes as **64 characters** (48 is divisible by 3).
- Values **change with random salt**; there is no fixed literal hash string for the same password.

The 96/64 lengths are for `Pbkdf2PasswordEncoder` output **without an `{id}` prefix**. When wrapped in `DelegatingPasswordEncoder`, the DB string length grows by the version prefix length. If an additional secret is used, the secret is not written as a plaintext prefix into the output string.

### Pbkdf2PasswordEncoder Storage Format Is Not Fully Self-Describing

`Pbkdf2PasswordEncoder` does not embed iteration count and PRF in a self-describing string format like some other password hash formats. It stores the salt and derived output formatted under the active configuration. Consequences:

- Changing `iterations` while reusing the same encoder for old records causes `matches` to fail.
- Changing PRF, salt length, secret, or Hex/Base64 mode without keeping a compatible decoder can prevent valid passwords from **logging in**.
- You cannot rely on a 96-character hash length to deduce the **exact** iteration count; multiple profiles sharing salt/key length produce the same output length.
- Store an **ID/profile version** alongside the password hash, typically via `DelegatingPasswordEncoder`'s `{id}` prefix.

**Wrong example:**

```java
// When creating the account:
Pbkdf2PasswordEncoder oldEncoder =
        Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();
String stored = oldEncoder.encode("correct-password");

// Later, config changes iterations without versioning:
Pbkdf2PasswordEncoder newEncoder = new Pbkdf2PasswordEncoder(
        "", 16, 600_000,
        Pbkdf2PasswordEncoder.SecretKeyFactoryAlgorithm.PBKDF2WithHmacSHA256
);

// Do not assume newEncoder.matches(..., stored) returns true.
// Old hashes need the old v5_8 encoder profile to verify.
```

The snippet above illustrates incompatible configuration, **not a standalone Java program**. The right approach is versioning, not "bumping rounds" across all records with a single config line.

## 6. `encode` and `matches`: Do Not Compare Newly Generated Hash Strings

`PasswordEncoder` has two operations:

```java
String savedHash = encoder.encode(rawPassword);
boolean accepted = encoder.matches(rawPassword, savedHash);
```

In PBKDF2 with random salts, two `encode` calls for the same raw password will **almost always** produce two different strings. Hence this pattern is wrong:

```java
boolean wrong = encoder.encode(submittedPassword).equals(storedHash);
```

You must use:

```java
boolean correct = encoder.matches(submittedPassword, storedHash);
```

Do not manually split salts or write a custom PBKDF2 verifier outside `PasswordEncoder` unless required by a specific protocol compatibility need; custom code easily gets character encoding, algorithm, output length, salt boundaries, and constant-time comparison wrong.

**Salt does not make weak passwords strong.** If a user sets `123456`, attackers can still guess it, merely paying the work factor per guess. Hash storage policy must accompany breached-password checks, appropriate MFA, rate limiting, and reasonable lockout/monitoring mechanisms.

## 7. Runnable Java 17 Example: Presets, Custom Parameters, and Versioning

This example uses **Spring Security 6.5.11, Gradle, and Java 17+**. It demonstrates:

- `v5_8` creating and verifying hashes.
- Salt and derived key having specific lengths per preset.
- `setEncodeHashAsBase64(true)` changing representation without making hashing stronger.
- A 600,000-iteration profile running and verifying accurately.
- `DelegatingPasswordEncoder` recognizing old hashes by `{id}` and writing new hashes with a new ID.

This is a **console** demo requiring no Spring Boot or DB connection. Never put sample passwords into production code.

### 7.1. Directory Structure

```text
pbkdf2-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/Pbkdf2Demo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'pbkdf2-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
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
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.Pbkdf2Demo'
}
```

### 7.2. `Pbkdf2Demo.java`

```java
package demo;

import java.util.Map;

import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder.SecretKeyFactoryAlgorithm;

public final class Pbkdf2Demo {

    public static void main(String[] args) {
        String password = "Tr0ngPa$!";

        Pbkdf2PasswordEncoder legacy =
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_5();
        Pbkdf2PasswordEncoder preset =
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();

        String presetHash = preset.encode(password);
        System.out.println("v58.hashHexChars=" + presetHash.length());
        System.out.println("v58.hexOnly="
                + presetHash.matches("[0-9a-fA-F]{96}"));
        System.out.println("v58.passwordRight="
                + preset.matches(password, presetHash));
        System.out.println("v58.passwordWrong="
                + preset.matches("wrong-password", presetHash));

        // Using another instance with the same profile still verifies the hash.
        Pbkdf2PasswordEncoder sameProfile =
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();
        System.out.println("v58.verifyAcrossInstances="
                + sameProfile.matches(password, presetHash));

        Pbkdf2PasswordEncoder base64 =
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();
        base64.setEncodeHashAsBase64(true);
        String base64Hash = base64.encode(password);
        System.out.println("v58.base64Chars=" + base64Hash.length());
        System.out.println("v58.base64Matches="
                + base64.matches(password, base64Hash));

        // Application's new profile: dedicated ID, without overwriting old ID semantics.
        Pbkdf2PasswordEncoder policy2026 = new Pbkdf2PasswordEncoder(
                "",
                16,
                600_000,
                SecretKeyFactoryAlgorithm.PBKDF2WithHmacSHA256
        );

        String tunedHash = policy2026.encode(password);
        System.out.println("policy2026.passwordRight="
                + policy2026.matches(password, tunedHash));
        System.out.println("policy2026.passwordWrong="
                + policy2026.matches("wrong-password", tunedHash));

        Map<String, PasswordEncoder> profiles = Map.of(
                "pbkdf2", legacy,
                "pbkdf2@SpringSecurity_v5_8", preset,
                "pbkdf2@policy2026", policy2026
        );

        DelegatingPasswordEncoder delegating =
                new DelegatingPasswordEncoder(
                        "pbkdf2@policy2026", profiles);

        String existingLegacy = "{pbkdf2}" + legacy.encode(password);
        String existingV58 =
                "{pbkdf2@SpringSecurity_v5_8}" + presetHash;

        System.out.println("legacy.matches="
                + delegating.matches(password, existingLegacy));
        System.out.println("v58.delegatedMatches="
                + delegating.matches(password, existingV58));
        System.out.println("v58.needsUpgrade="
                + delegating.upgradeEncoding(existingV58));

        String newStored = delegating.encode(password);
        System.out.println("new.hasPolicyId="
                + newStored.startsWith("{pbkdf2@policy2026}"));
        System.out.println("new.matches="
                + delegating.matches(password, newStored));
    }
}
```

### 7.3. Run Command and stdout

From the `pbkdf2-demo` directory, with JDK 17+ and a Java 17-compatible Gradle (or equivalent Gradle Wrapper) installed:

```bash
gradle run --quiet
```

The `System.out.println` stdout lines **under the given configuration and program code**, excluding environment build/log messages:

```text
v58.hashHexChars=96
v58.hexOnly=true
v58.passwordRight=true
v58.passwordWrong=false
v58.verifyAcrossInstances=true
v58.base64Chars=64
v58.base64Matches=true
policy2026.passwordRight=true
policy2026.passwordWrong=false
legacy.matches=true
v58.delegatedMatches=true
v58.needsUpgrade=true
new.hasPolicyId=true
new.matches=true
```

Specific hashes are generated with random salts, so **do not attempt to print literal hash strings**. Boolean results and lengths can be verified deterministically on the stated profile, while hash values change with every `encode` call. The example assumes the JDK/JCA provider supports `PBKDF2WithHmacSHA256` — standard on modern JDK 17.

### 7.4. Breakdown of Each Result Group

- **`v58.hashHexChars=96`:** 16 bytes of salt + 32 bytes of derived key = 48 bytes, with two Hex characters per byte.
- **`v58.passwordRight=true` and `passwordWrong=false`:** passwords are checked via `matches` rather than comparing two `encode` outputs.
- **`verifyAcrossInstances=true`:** when secret, PRF, iterations, saltLength, and output encoding match, a new instance still verifies old hashes. It does not depend on Java object identity.
- **`base64Chars=64`:** the same profile using Base64 output; output length differs from Hex. The same representation config is required during verification.
- **`policy2026.passwordRight=true`:** selects 600,000 rounds via the current constructor; the demo avoids asserting CPU timing since it depends on hardware.
- **`legacy.matches=true`:** the registry still supports the old profile under id `pbkdf2`. Do not remove the legacy decoder before all records have migrated.
- **`v58.needsUpgrade=true`:** `DelegatingPasswordEncoder` sees the old record has a different ID from the encoding ID. This is a signal that it **can** be upgraded when the app has an appropriate password-update flow; it does not auto-rewrite the DB in the demo.
- **`new.hasPolicyId=true`:** the new hash carries its own ID, ensuring later verification maps back to the 600,000-round parameter set rather than assuming `pbkdf2@SpringSecurity_v5_8`.

**Important distinction:** IDs in `profiles` are *application-defined labels*. `pbkdf2@policy2026` is not a built-in Spring Security factory preset; it works only because the `Map` registered that key. Use meaningful IDs and never mutate the profile definition an existing ID previously represented.

## 8. `DelegatingPasswordEncoder` Format and Version Confusions

Spring Security provides `DelegatingPasswordEncoder` to store:

```text
{id}encodedPassword
```

Examples:

```text
{pbkdf2}...
{pbkdf2@SpringSecurity_v5_8}...
{pbkdf2@policy2026}...
{bcrypt}$2a$...
```

**The prefix is not a self-executing algorithm.** It selects the `PasswordEncoder` object with the matching ID in the registry. At verification, `DelegatingPasswordEncoder` strips `{id}`, looks up the encoder in the `Map`, and passes the remainder to that encoder. If mapping/id is missing, verification may fail or throw an error; **never** guess a PBKDF2 profile by "trying them all" without a security policy.

### 8.1. The Default Factory Does Not Default to PBKDF2

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` builds a registry containing multiple encoders. In the Spring Security 6.5 branch, the ID used to **encode new passwords by default** is `bcrypt`; the registry can also support `pbkdf2` (legacy profile) and `pbkdf2@SpringSecurity_v5_8` (v5_8 profile) for matching corresponding data.

```java
PasswordEncoder factory =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

// With the default factory in Spring Security 6.5,
// new passwords normally receive the {bcrypt} prefix, not {pbkdf2}.
String stored = factory.encode("DemoPass123!");
```

If a product chooses PBKDF2 as its write profile, it **must explicitly configure `DelegatingPasswordEncoder`** as in section 7 or an equivalent organizational registry. Do not confuse "PBKDF2 is in the readable list" with "PBKDF2 is selected for writing".

### 8.2. Do Not Reassign New Config to an Already Used ID Name

Suppose the DB contains:

```text
{pbkdf2@SpringSecurity_v5_8}HEX_WITH_16_BYTE_SALT_AND_310000_ITERATIONS
```

If tomorrow the code changes the `pbkdf2@SpringSecurity_v5_8` mapping to a **600,000-round** encoder while keeping the old ID, users with valid passwords will fail verification. Keep the old ID bound to the old parameters, and create `pbkdf2@policy2026` or a similar versioned profile ID for writing new records.

**Migration note:** the `{id}` prefix distinguishes profiles only when each ID binds to **one immutable configuration**. If an organization reused the same ID across multiple PRFs/work factors/secrets without metadata, old records may be unclassifiable. In that case, analyze the data and prepare a verification/password-change flow; never patch hashes by arbitrarily swapping prefixes.

## 9. Safely Upgrading the Work Factor for Existing Data

A long-running system may have multiple hash profiles:

| Record group | ID | Action needed |
| --- | --- | --- |
| Legacy PBKDF2 | `pbkdf2` | Keep **verify-only** capability during transition; never use for new hashes. |
| PBKDF2 v5_8 | `pbkdf2@SpringSecurity_v5_8` | Verify with old parameters; flag as needing upgrade per policy. |
| New PBKDF2 policy | `pbkdf2@policy2026` | Write new hashes with current parameters; never change ID arbitrarily. |
| Existing BCrypt | `bcrypt` | If historical data exists of this type, keep the decoder until migration is complete. |

**Migration roadmap:**

1. **Inventory** existing hash formats: presence of `{id}`, parameters behind each ID, Hex/Base64 format, whether a server-side secret is used, and any legacy hashes with unknown profiles.
2. **Freeze old ID semantics**: the verification registry must keep objects matching old profiles, without editing them in place.
3. **Create a new ID** for the post-benchmark configuration, e.g., PBKDF2-HMAC-SHA256/600,000/salt16/Hex.
4. **Switch write paths** (registration, password change, reset) to the new encoder while continuing to verify old records.
5. **Rehash after successful authentication**: only then is the correct raw password present in the auth flow; re-encode with the new profile and safely update the DB inside a transaction.
6. **Handle concurrency**: prevent a new hash update from overwriting another password change; use versioning/optimistic locking or compare-and-set by design.
7. **Track progress**: gather metrics by hash ID, login latency, error rates, and remaining legacy records, without logging raw passwords.
8. **Plan for inactive accounts**: define a secure password reset/recovery policy; you cannot arbitrarily rehash an old hash into a new hash without knowing the raw password.
9. **Remove the legacy decoder only** once verified zero records need it, with backups/rollback and thorough testing.
10. **Manage secret changes separately**: if a server-side pepper/secret exists, changing secrets needs explicit versioning and the ability to retain or rotate old keys per policy.

### 9.1. `upgradeEncoding` and `UserDetailsPasswordService`

`PasswordEncoder.upgradeEncoding(encodedPassword)` reports whether a stored hash needs an upgrade under the encoder's policy. With `DelegatingPasswordEncoder`, a record with an **ID different from the write ID** is typically flagged for upgrade.

`DaoAuthenticationProvider` can be configured with `UserDetailsPasswordService` to update password hashes after successful authentication when the encoder signals an upgrade is needed.

Wiring outline:

```java
// Spring Security snippet, not a standalone Java program.
// usersService implements UserDetailsService;
// passwordUpdateService implements UserDetailsPasswordService.
DaoAuthenticationProvider provider =
        new DaoAuthenticationProvider(usersService);
provider.setPasswordEncoder(delegatingPasswordEncoder);
provider.setUserDetailsPasswordService(passwordUpdateService);
```

`UserDetailsPasswordService.updatePassword(user, newPassword)` receives the **password already encoded** with the new encoder, not the raw password. Implementations must update the matching record and return an appropriate `UserDetails`. Do not enable automatic migration if DB updates lack concurrency control, version metadata policies, or a secret-rotation plan.

**Important:** do not rely on `Pbkdf2PasswordEncoder` *alone* to extract iteration counts from old hash strings. The ID/profile mechanism and upgrade process are designed by the application.

## 10. Benchmarking Iterations and Balancing Security/Operations

There are two simultaneous goals:

1. **Make offline password guessing expensive** if an attacker compromises the hash database.
2. **Avoid overloading the login server** due to excessive verification cost or request floods.

Spring Security suggests tuning so password verification takes a noticeable amount of time on the target machine; OWASP provides updated reference thresholds for PBKDF2-HMAC-SHA256. **Neither replaces product-specific benchmarking**.

A useful measurement plan:

- Choose a JDK, JCA provider, OS, and CPU specification matching production.
- Use sample passwords of realistic lengths plus some longer cases; never log real passwords.
- Warm up the JVM and measure sufficient verification iterations rather than taking a cold first call.
- Measure `p50`/`p95`/`p99` percentiles alongside CPU utilization, not only the mean.
- Simulate concurrent logins within operational limits, tracking throughput and queueing.
- Measure inside containers with real CPU quotas, not an unconstrained laptop.
- Combine rate limiting, anti-credential stuffing, timeouts, circuit breakers/failure strategies, and scaling plans as needed.
- If raising from 310,000 to 600,000 pushes latency past your SLO, evaluate architecture/hardware and risk trade-offs instead of blindly lowering to an easily guessable number.

**Never benchmark by running unbounded PBKDF2 loops in production.** Use a controlled load environment. And never expose a public endpoint for "quick benchmarking" where attackers could force the server into endless KDF rounds.

## 11. Role of `Pbkdf2PasswordEncoder` in Spring Security Authentication

In the username/password flow:

```text
Client sends username / raw password
          |
          v
Spring Security authentication filter
          |
          v
AuthenticationManager (ProviderManager)
          |
          v
DaoAuthenticationProvider
    |
    +--> UserDetailsService.loadUserByUsername()
    |        |
    |        +--> retrieve username, passwordHash, flags, authorities
    |
    +--> account-state checks
    |
    +--> PasswordEncoder.matches(rawPassword, passwordHash)
    |
    +--> credential-expiry checks
          |
       Result:
        ├── valid and active → authenticated Authentication
        └── invalid/blocked → AuthenticationException
```

`Pbkdf2PasswordEncoder` only handles **password hashing/verification**; it does not do three other things:

- It does not load users from JPA, JDBC, or LDAP: that belongs to `UserDetailsService`/identity stores.
- It does not grant authorities or populate `SecurityContext`: the provider/filter manages the authentication flow.
- It does not migrate all old hashes in the DB to new parameters automatically: that requires `DelegatingPasswordEncoder`, an update service, and a migration policy.

An illustrative Spring Boot Servlet configuration, assuming a database-backed `UserDetailsService` bean already exists:

```java
@Configuration
class PasswordSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        Pbkdf2PasswordEncoder v58 =
                Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();

        Pbkdf2PasswordEncoder policy2026 = new Pbkdf2PasswordEncoder(
                "", 16, 600_000,
                Pbkdf2PasswordEncoder.SecretKeyFactoryAlgorithm
                        .PBKDF2WithHmacSHA256);

        return new DelegatingPasswordEncoder(
                "pbkdf2@policy2026",
                Map.of(
                        "pbkdf2@SpringSecurity_v5_8", v58,
                        "pbkdf2@policy2026", policy2026));
    }
}
```

This is a **configuration excerpt**, requiring the remaining imports and application beans/services. If the DB contains `{bcrypt}` or legacy `{pbkdf2}`, **this example registry lacks decoders for them** — add the required entries before production use. If the database previously stored plain PBKDF2 **without prefixes**, execute a controlled format migration rather than swapping the bean and hoping login keeps working.

In production, the password encoder bean must be a **consistent singleton/configuration** per application version, never reading iteration counts from client requests. Never log raw passwords, salts, full encoded hashes, or additional secrets; while salt is not secret, the complete hash remains a sensitive credential verifier to protect.

## 12. Testing: Correct Parameters Are Not Enough Without Storage Contracts

### 12.1. Required Encoder-Level Tests

| Test | Behavior to Verify |
| --- | --- |
| Encode right password | `matches(raw, encoded) == true`. |
| Encode and test wrong password | `matches(wrong, encoded) == false`. |
| Different salts | Multiple `encode` calls normally produce different hashes; collision probability is tiny. |
| Default Hex output | For v5_8: 96 Hex characters, without `{id}`. |
| Base64 output | For v5_8 + `setEncodeHashAsBase64(true)`: 64 Base64 characters; matches under same profile. |
| Cross-instance verification | Hash created by one instance verifies on another instance with identical config. |
| Legacy ID | `DelegatingPasswordEncoder` accepts `{pbkdf2}` matching the old profile. |
| Version v5_8 ID | Registry matches `{pbkdf2@SpringSecurity_v5_8}`. |
| New profile ID | New hashes carry the active write policy ID prefix and verify properly. |
| Version mismatch | Do not expect passwords to verify with different iterations/PRF; migration retains old decoders. |
| Unknown ID | Never approve logins by guessing; handle errors in a controlled manner. |
| Unicode passwords | No arbitrary `trim()`/`toLowerCase()`/normalization in login adapters; preserve exact user-set strings. |

With random salts, **never assert a hash against a hardcoded string literal**. `encode` output varies per run; unit tests should assert properties, lengths, IDs, and verification behavior.

### 12.2. Testing from DB to Provider

Use a real `UserDetailsService` or a controllable test adapter store:

1. Create a user with password hash `{pbkdf2@SpringSecurity_v5_8}...`.
2. Configure `DelegatingPasswordEncoder` with a mapping for that ID.
3. Call `AuthenticationManager.authenticate(UsernamePasswordAuthenticationToken.unauthenticated(username, rawPassword))`.
4. Verify the provider authenticates successfully and authorities come from the trusted source.
5. Repeat with a wrong password; expect `BadCredentialsException` and no authenticated token.
6. For a disabled/locked account, even the right password must not succeed.
7. If `UserDetailsPasswordService` is configured, confirm the hash upgrades properly after a valid login and remains usable on the next login.
8. Test concurrency between a hash-upgrading login and an actual password change, preventing lost updates.
9. Test across restarts with the encoder bean rebuilt from config: **old hashes must still verify**.
10. Test rollbacks/multi-instance deploys: can older nodes read the new ID prefix? Never let some nodes emit new hashes before other nodes have the decoder.

**`@WithMockUser` does not prove PBKDF2 ran.** That annotation places a mock authentication directly into the test; to verify the real encoder, invoke the provider or an HTTP login through the corresponding filter chain.

### 12.3. Verifying v5_5 → v5_8 → New Profile Migration

A proper migration looks like:

```text
Existing records:
  {pbkdf2}...                        --> verified with v5_5
  {pbkdf2@SpringSecurity_v5_8}...    --> verified with v5_8

Successful login:
  raw password exists only within the authentication flow
         |
         +--> DelegatingPasswordEncoder.matches(...)
         |
         +--> upgradeEncoding(...) == true
         |
         +--> encode(raw) using the new idForEncode
         |
         +--> UserDetailsPasswordService updates hash in DB

New record:
  {pbkdf2@policy2026}...             --> verified with 600000 profile
```

Never take a PBKDF2 v5_5 string as a "raw password", run another PBKDF2 layer over it, and save it. That produces a **hash of a hash**, breaking authentication against the user's actual raw password. Only rehash after knowing the verified password or requiring a user reset.

## 13. Common Security and Operational Mistakes

1. **Using standalone SHA-256 for passwords** thinking it equals PBKDF2-HMAC-SHA256. It lacks the work factor and salt structure.
2. **Storing plaintext or unnecessary reversible encryption.** A DB/key leak exposes passwords en masse.
3. **Setting `saltLength=16` thinking it means 16 bits.** The constructor takes bytes: 16 bytes = 128 bits.
4. **Setting `iterations=310000` thinking the hash will be 310000 characters long.** Iterations is the round count, not string length.
5. **Assuming a 256-bit hash means HMAC-SHA256 runs 256,000 rounds.** Those two parameters are completely unrelated.
6. **Writing `encode(input).equals(stored)`.** Random salts make string equality fail; use `matches`.
7. **Changing iterations under the same stored ID** without keeping the old profile decoder. Valid passwords stop verifying.
8. **Rotating secret/pepper without versioning and a recovery plan.** Can render all old hashes unverifiable.
9. **Toggling `setEncodeHashAsBase64` without classifying old data.** Hex and Base64 formats differ and need separate mappings.
10. **Assuming `{pbkdf2}` and `{pbkdf2@SpringSecurity_v5_8}` are identical configs.** In the 6.5 factory they map to different presets.
11. **Assuming the default factory encodes with PBKDF2.** `PasswordEncoderFactories.createDelegatingPasswordEncoder()` in 6.5 normally writes new hashes with bcrypt.
12. **Setting work factor too high and forgetting concurrency limits.** The login endpoint can become a CPU exhaustion DoS target.
13. **Lowering production work factor just to make tests fast without re-evaluating.** Offline brute-force risk rises; tests may use a separate profile while still verifying real compatibility.
14. **Deleting the legacy encoder immediately when deploying a new algorithm.** Users who have not logged in yet to migrate can no longer authenticate.
15. **Prepending an `{id}` prefix without knowing the exact old profile.** A wrong prefix breaks verification.
16. **Reusing one ID across multiple different configurations.** Makes deterministic interpretation/verification of old hashes impossible.
17. **Encoding as Base64 and thinking the hash is stronger than Hex.** It is solely a data representation, adding neither rounds nor entropy.
18. **Hard-coding secrets in source and logging hashes/passwords.** Defeats server-side secret protection and increases credential-verifier exposure.
19. **Calling the encoder in a controller instead of a provider** and minting `Authentication` whenever username matches. Can bypass account-state checks and authority mapping.
20. **Confusing PBKDF2 with JWT or session encryption.** It is a password-verifier storage choice; tokens/sessions use separate security mechanisms.
21. **Confusing "FIPS-friendly" with "FIPS-certified".** Actual modules/providers and deployment modes must be evaluated.
22. **Relying on a single laptop run's speed as a universal work factor.** Production concurrency and CPU quotas can behave very differently.
23. **Assuming SHA-512 is always stronger than SHA-256 without updating policy.** PRF, iterations, and output length must be chosen and versioned together.
24. **Using password hashes as public user IDs/tokens.** Encoded passwords are sensitive verification data; never expose them in APIs or URLs.
25. **Changing configuration mid-rolling-deploy directly.** Older nodes may not recognize new IDs, causing intermittent login failures.
26. **Putting a sample password into production code** because the Gradle example runs. Secrets must flow through secure configuration and never be committed to the repository.

## 14. Self-Check Questions

**Question 1.** How does `Pbkdf2PasswordEncoder` differ from `MessageDigestPasswordEncoder("SHA-256")`?

**Answer:** PBKDF2 uses a salt and many iterations with HMAC, making each password guess significantly more resource-intensive. Standard SHA-256 hashing is far too fast for safe password storage.

**Question 2.** Does `saltLength=16` mean 16 bytes or 16 bits? In the v5_8 preset, how long is the unprefixed Hex string?

**Answer:** 16 bytes = 128 bits. 16 bytes of salt plus 32 bytes of derived key equals 48 bytes; Hex length is 96 characters.

**Question 3.** Two users have the same password and two different `encode` outputs; is one password wrong?

**Answer:** No. Different random salts yield different encoded hashes. `matches` reads the salt from each record to verify.

**Question 4.** Why can old user logins fail after changing from 310,000 to 600,000 rounds?

**Answer:** PBKDF2 output does not fully self-describe the iteration count; verifying a 310,000-round hash with a 600,000-round encoder is incompatible. Keep the old profile under its ID and upgrade when a valid raw password is available.

**Question 5.** Does `setEncodeHashAsBase64(true)` increase brute-force difficulty?

**Answer:** No. Base64 only changes how the salt + derived key bytes are represented; PRF, iterations, and entropy stay unchanged.

**Question 6.** In Spring Security 6.5, does `PasswordEncoderFactories.createDelegatingPasswordEncoder()` write new hashes with PBKDF2 by default?

**Answer:** No; the default factory normally writes new hashes with bcrypt. To use PBKDF2 as the write profile, configure the corresponding ID and registry explicitly.

**Question 7.** Is a `{pbkdf2}...` hash automatically interpreted as the v5_8 profile?

**Answer:** No. In the 6.5 default registry, `pbkdf2` maps to the legacy v5_5 preset, while `pbkdf2@SpringSecurity_v5_8` maps to the v5_8 profile.

**Question 8.** Does `DelegatingPasswordEncoder.upgradeEncoding` returning true mean the DB updates immediately?

**Answer:** No. You need a mechanism capturing the raw password after successful authentication and a service persisting the new hash, such as `UserDetailsPasswordService` with transaction/concurrency control.

**Question 9.** Does 310,000-round PBKDF2-HMAC-SHA256 automatically meet current OWASP baselines?

**Answer:** No. OWASP currently cites 600,000 rounds for PBKDF2-HMAC-SHA256 in the relevant guidance; review policy, timing, benchmarks, and product environment.

**Question 10.** Are salt and the additional secret the same thing?

**Answer:** No. Salt is public and generated uniquely per encode; the additional secret, if used, is kept secret server-side. Changing the secret without version management makes old hashes hard or impossible to verify.

**Question 11.** Can you switch SHA256 to SHA512 while keeping the same prefix ID without checking existing data?

**Answer:** No. The HMAC PRF is part of the profile; changing it requires a new ID and keeping the old decoder during migration.

**Question 12.** Why is a `@WithMockUser` test insufficient to prove the password encoder works?

**Answer:** Mock users typically populate the security context directly without passing through `DaoAuthenticationProvider` and `matches`. You must test the real provider or HTTP login through the filter chain.

## 15. Official References and Adoption Checklist

Sources to read directly before deciding production policy:

- [Spring Security 6.5 — Pbkdf2PasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/Pbkdf2PasswordEncoder.html): constructors, v5_5/v5_8 presets, `setEncodeHashAsBase64`, and algorithms.
- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): `PasswordEncoder`, `DelegatingPasswordEncoder`, `{id}encodedPassword` format, and encoders by ID.
- [Spring Security 6.5 — Crypto Module](https://docs.spring.io/spring-security/reference/6.5/features/integrations/cryptography.html): how to use PBKDF2 and verification-time tuning notes.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): username/password verification with `UserDetailsService` and `PasswordEncoder`.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): salt, work factor, PBKDF2-HMAC-SHA256, 600,000-round profile, and migration.
- [NIST SP 800-63B-4 — Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html): salted password hashing, cost factors, version metadata, and operational requirements.
- [Oracle Java 17 — SecretKeyFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html): JCA API used for PBKDF2 key derivation.

**Pre-deployment checklist:**

- Selected a clear PBKDF2 profile defining `PRF + iterations + salt bytes + output format + secret policy`.
- Benchmarked verification in a production-like environment with realistic concurrency.
- Separated legacy profiles, Spring presets, and new write profiles using versioned IDs.
- Database stores the full hash and ID without string truncation.
- Login service verifies via `matches` through the provider, never comparing two `encode` calls.
- Login limits/rate limiting and anti-credential-stuffing controls are in place.
- Tests cover provider/HTTP login, multi-version verification, migration, and rollback.
- Secret lifecycle plan exists if using a pepper, and the secret is never stored in the DB.
- No passwords, full hashes, or sensitive details are logged.
- Policy exists for raising work factors over time without silently mutating old ID configurations.

**Conclusion:** `Pbkdf2PasswordEncoder` produces password verifiers via **salted PBKDF2 with tunable iteration cost**. Security does not lie in a single `encode` call alone: choose a suitable PRF and work factor, keep configurations consistent during `matches`, version every change, protect secrets, and execute migrations safely. In Spring Security 6.5, the v5_8 preset uses **16-byte salt, PBKDF2-HMAC-SHA256, 310,000 iterations, and a 256-bit derived key**, while modern production policies may require different settings after consulting OWASP and real benchmarks.