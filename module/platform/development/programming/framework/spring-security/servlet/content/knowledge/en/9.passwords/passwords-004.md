# BCrypt, PBKDF2, SCrypt, and Argon2: Selection Criteria in Spring Security

When storing passwords for Spring Security Servlet application accounts, the question is not just "which algorithm is the strongest?". You need to choose a **password hashing/KDF designed for passwords**, balancing resistance against offline password guessing, server CPU/RAM consumption, system compatibility requirements, operational cost, and an upgrade path for existing hashes. Four common names are **BCrypt, PBKDF2, SCrypt, and Argon2**. There is no single fixed cost/iterations/memory value that is optimal for every product.

This lesson focuses on selection criteria and how to use the algorithms via `PasswordEncoder` in **Spring Security 6.x on the Servlet stack**, with Java 17+ and Spring Boot 3.x examples. Parameters and API versions in the examples are illustrative: before production deployment, benchmark on target hardware, account for login traffic, and test the entire migration.

## 1. Understanding the true goal: storing passwords for verification, not recovery

At registration or password change, the application receives a **raw password** over a protected channel (HTTPS), uses a salted/cost-tuned password hashing algorithm to generate an **encoded password**, and stores the encoded value in the database. At login, the application does not decrypt this value; it checks the entered password against the stored value.

~~~text
Registration/password change:
raw password ---- password KDF + random salt + work factors ---> encoded hash
                                                               |
                                                               v
                                                             database

Login:
raw password + encoded hash ---- PasswordEncoder.matches(...) ---> true/false
~~~

Spring Security represents that operation through `org.springframework.security.crypto.password.PasswordEncoder`:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

This is **a contract outline for learning**, not an interface declaration to copy into your project. `encode` creates the stored value; `matches` returns the verification result; `upgradeEncoding` helps decide whether the stored hash needs an upgrade, though it **does not automatically update the database**.

Mandatory principles:

- **Never store plaintext**, and do not use reversible encryption so you can "recover the password" when a user forgets it. A forgot-password flow should issue a password reset token, not send back the old password.
- **Never use fast hashes** like MD5, SHA-1, or plain SHA-256 (even with salt) to store passwords. Those functions are optimized for speed, allowing attackers to test passwords very rapidly on GPUs/ASICs.
- **A unique salt per password** means the same password usually produces different encoded hashes; salt is not a secret and is typically packaged inside the stored hash. No separate salt column is needed if the encoder format already embeds it.
- **Work factor** (iterations/cost/memory/parallelism) makes each password attempt costly enough to impede bulk guessing. Consequently, it also increases resource usage when legitimate users log in.
- **Pepper** is an application secret used outside the database (depending on system design), not a replacement for salt or a strong algorithm. If using a pepper, design HSM/secret manager storage, lifecycle, and rotation; never append a hardcoded string to passwords and call it secure.
- **Never compare** `encoder.encode(password).equals(storedHash)`: many algorithms generate a new salt on every encode, so hashes differ even for the same raw password. Always use `matches`.

The primary threat model here is **an adversary who has obtained the database containing password hashes** and tests candidate passwords offline. In that case, rate limiting on the login endpoint **does not** directly slow down their offline guessing; the algorithm's cost, password entropy, and other security controls determine resilience. Conversely, against online attacks, rate limiting/MFA/login alerts remain vital.

## 2. Quick comparison of the four algorithms

| Criterion | BCrypt | PBKDF2 | SCrypt | Argon2 (prefer Argon2id in general use) |
| --- | --- | --- | --- | --- |
| Core idea | Repeated password hashing with exponential cost | Key derivation via iterated PRF/HMAC | Password KDF requiring both CPU and memory | Password KDF designed with configurable RAM/time/lanes cost |
| Primarily constrained by | CPU/time | CPU/time | CPU + RAM | CPU + RAM, with parallelism parameter |
| Common parameters | Cost/work factor | Iterations, PRF, salt/key length | N, r, p (cost, block size, parallelization) | m, t, p (memory, iterations, parallelism) |
| Salt | Typically embedded in encoded hash | Requires random salt; encoder usually stores alongside | Random salt, stored alongside by encoder | Random salt, stored alongside by encoder |
| Strengths | Widely used, mature, easy compatibility | Many implementations, easy to satisfy ecosystem/standards constraints | Memory-hard, penalizes large-scale parallel guessing | Memory-hard, explicit cost tuning, fits many modern threat models |
| Caveats | BCrypt input has an effective limit around 72 bytes; not memory-hard like SCrypt/Argon2 | Not memory-hard; needs high enough iterations and careful PRF choice | RAM and CPU load must account for concurrency; depends on implementation library | Requires memory budget, library support, and benchmarking; choose the **Argon2id variant** when appropriate |
| In Spring Security | `BCryptPasswordEncoder` | `Pbkdf2PasswordEncoder` | `SCryptPasswordEncoder` | `Argon2PasswordEncoder` |
| Suitable scenario | Java system needing mainstream password hashing with simple ops | Environment needing PBKDF2 compatibility or specific compliance constraints | Want memory-hard where stack supports SCrypt well | New system prioritizing memory-hard with adequate RAM budget |
| Is there an "absolute strongest"? | No | No | No | No |

**Key takeaway:** "Argon2 is stronger" is not a sufficient statement for production selection, because an under-configured Argon2 can still be weaker than another properly benchmarked configuration. Likewise, BCrypt with too low a cost or PBKDF2 with too few iterations can offer weak protection. Compare **parameters, hardware, threat model, and actual implementation**, not just algorithm names.

If an organization has compliance requirements such as FIPS, verify the **exact library/provider, mode of operation, and certification scope**. PBKDF2 is often considered in such constrained environments, though the algorithm name PBKDF2 alone does not prove the entire deployment is FIPS-compliant.

## 3. BCrypt: a steady choice when simplicity and compatibility matter

BCrypt applies a password-focused hash mechanism with salt and cost. In Spring Security:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);

String stored = encoder.encode("example-password");
boolean correct = encoder.matches("example-password", stored);
boolean wrong = encoder.matches("wrong-password", stored);
~~~

This is an **illustrative snippet** requiring imports for `PasswordEncoder` and `BCryptPasswordEncoder`; it is not a standalone Java file. `12` is an example cost, **not** a fixed recommendation. `correct` is `true` and `wrong` is `false` when the encoder operates normally; `stored` varies by salt, so do not put a fixed hash in assertions.

### 3.1. Cost in BCrypt

BCrypt's work factor is usually expressed as an integer; processing cost grows very rapidly as cost increases, roughly exponentially. Moving from cost 10 to 12 does not mean "20% more effort"; intuitively, it multiplies the work rounds severalfold, though actual latency must be measured.

What to measure goes beyond a single `encode` call on a laptop:

- `matches` duration at key percentiles (p50, p95, p99) on **production hardware**.
- Concurrent authentication requests, traffic bursts, and queue times.
- Container CPU limits, noisy neighbors, and cold start times.
- Headroom to raise cost in the next 1–2 years and how to upgrade old hashes.

BCrypt parameters are stored in the hash format, allowing the encoder to determine the cost during verification; no separate table recording per-user cost is needed when using the library's standard format.

### 3.2. The ~72-byte input limit

BCrypt has an effective input limit around **72 bytes**, not 72 Unicode characters. In UTF-8, a single character can take multiple bytes. Many BCrypt implementations only examine the leading portion of the input past the limit; two strings sharing the same byte prefix can cause compatibility and security issues if the product handles them inconsistently.

When choosing BCrypt:

1. Define how passwords convert to bytes and set reasonable, consistent limits across registration, login, password change, and migration.
2. Test long passwords and multi-byte Unicode strings.
3. Do not silently truncate password strings by character count without explaining the policy to users.
4. Do not place a custom pre-hash algorithm in front of BCrypt without serious protocol and versioning design: such a change alters the password definition and can cause incompatibilities.

### 3.3. When is it appropriate?

BCrypt is often reasonable if the team wants a ubiquitous, long-supported solution that operates primarily on CPU. For new systems that can allocate substantial RAM per attempt, also evaluate Argon2id. For legacy systems already storing BCrypt, you do not need to force all accounts to change passwords just to switch algorithms immediately; a migrate-on-successful-login roadmap is usually better.

## 4. PBKDF2: prioritizing compatibility and ecosystem requirements

PBKDF2 iterates a pseudorandom function (usually HMAC with a chosen hash) many times over the password and salt to derive a key/hash. It primarily consumes CPU and is widely supported across cryptographic libraries.

Spring Security includes `Pbkdf2PasswordEncoder`. On Spring Security 6.x, a versioned factory is provided to select parameter sets matching a specific profile:

~~~java
PasswordEncoder encoder =
    Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();

String stored = encoder.encode("example-password");
boolean correct = encoder.matches("example-password", stored);
~~~

The above is a **code snippet**, not a standalone runnable program; it requires importing `Pbkdf2PasswordEncoder` and `PasswordEncoder`. Versioned factories avoid arbitrarily copying iteration/salt-length numbers. However, **do not treat a release default as a mandatory setting for every system or assume it always reflects the latest standards**: in production, policy evaluation and benchmarking are still required.

### 4.1. Key parameters

- **PRF**: for example HMAC-SHA256. Must be specified explicitly when exchanging hashes across systems.
- **Iterations**: higher counts increase CPU cost; a small setting can become inadequate over time.
- **Salt**: random, unique per password, with sufficient length per policy.
- **Derived key length**: output size; doubling the length does not double resistance against password guessing.
- **Optional secret/pepper**: if using the implementation's secret-mixing feature, the secret must be managed and versioned separately.

### 4.2. Advantages and limitations

PBKDF2 is advantageous when a project must interoperate with a system standardized on PBKDF2 or operates under cryptographic/compliance constraints. It can run easily in runtimes lacking suitable memory-hard libraries.

The important limitation is that PBKDF2 is **not memory-hard** like SCrypt/Argon2id. Adversaries with strong parallel hardware can test candidates more cost-effectively than against a RAM-intensive KDF, depending on parameters and environment. Thus, "very high iterations" is not a free solution: the server must also execute that work for every legitimate authentication.

### 4.3. Common mistakes

- Using PBKDF2 with iteration counts frozen for many years.
- Not storing or identifying the PRF, iterations, and salt length configuration when upgrading encoder versions.
- Changing implementation/secret/PRF without retaining a mechanism to verify old hashes.
- Citing PBKDF2 by name as proof of FIPS compliance without checking the certified provider/environment.
- Using a fast single-pass PBKDF2 with weak passwords and expecting it to solve credential stuffing; online attacks still need defense in depth.

## 5. SCrypt: raising RAM cost to resist parallel guessing

SCrypt is a memory-hard password KDF. Beyond CPU, anyone testing passwords must allocate memory for intermediate computations; this makes large-scale parallel attacks require significantly more RAM.

In Spring Security, the class is `SCryptPasswordEncoder` (note the uppercase `SCrypt`):

~~~java
PasswordEncoder encoder =
    SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8();

String hash = encoder.encode("example-password");
boolean valid = encoder.matches("example-password", hash);
~~~

Import `org.springframework.security.crypto.scrypt.SCryptPasswordEncoder` and `PasswordEncoder`. Depending on version and packaging, Spring Security's SCrypt implementation requires an additional crypto dependency such as Bouncy Castle; verify the runtime classpath, not just compilation.

### 5.1. How do N, r, p behave?

SCrypt parameters are commonly described as:

- **N** (cost/work factor): amount of work, typically constrained to powers of 2.
- **r** (block size): affects RAM usage and computation.
- **p** (parallelization): number of independent mixing blocks that can increase effort.

A well-known estimate for the core memory portion is roughly **128 × N × r bytes**, though total actual memory across the library/JVM, buffers, thread stacks, GC, and concurrent requests involves many more factors. Never use the formula as a substitute for measuring **RSS/heap/native memory** under real load.

### 5.2. When to choose SCrypt

SCrypt fits when a system wants memory-hardness, the implementation is well supported, and RAM budgets accommodate it. Do not raise `N, r, p` by intuition. If a machine handles 1,000 concurrent login requests and each attempt demands substantial RAM, the application can suffer memory pressure or `OutOfMemoryError` even when isolated requests succeed.

Enforce concurrency limits and protect the authentication endpoint from resource exhaustion. Memory-hardness makes measuring cost in containerized environments and under load more important, not less.

## 6. Argon2: prefer Argon2id when it fits the threat model

Argon2 is a family of password hashing/KDFs with multiple variants. In most modern password storage designs, **Argon2id** is generally preferred because it combines resistance against certain side-channel attacks and specialized hardware computation. Do not lump all "Argon2" configurations together without knowing the variant and parameters.

In Spring Security 6.x:

~~~java
PasswordEncoder encoder =
    Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();

String hash = encoder.encode("example-password");
boolean valid = encoder.matches("example-password", hash);
~~~

Import `org.springframework.security.crypto.argon2.Argon2PasswordEncoder` and `PasswordEncoder`. Spring Security's implementation delegates to the corresponding crypto backend, typically requiring Bouncy Castle on the classpath. Ensure the proper dependency is present; a missing library can cause runtime failures even when the code compiles.

### 6.1. Memory, iterations, and parallelism

Three parameter groups you must understand:

- **m / memory cost**: amount of memory used by the algorithm. This is the key differentiator compared to CPU-only KDFs.
- **t / iterations or passes**: number of computational passes; increasing this generally increases time.
- **p / parallelism**: number of lanes/degree of algorithmic parallelism; affects how the implementation consumes resources.

There are also salt length, hash length, Argon2 variant, and version format. These parameters should be tied to an **encoding policy version** so stored hashes can be verified and upgraded cleanly in the future.

Never adopt parameters from a benchmark table for a different CPU/RAM setup without measuring. Especially on Kubernetes, serverless, or low-RAM instances, memory cost per concurrent request can degrade throughput or trigger pod OOM kills.

### 6.2. What makes Argon2id a good choice?

Requiring RAM raises the cost of parallel guessing across many GPU/ASIC setups, while the server can deliberately budget RAM per hash operation. For new applications, Argon2id is often a top candidate **if** the runtime and operations can support a reasonable memory cost.

Even so, never assume "any Argon2id API call with arbitrary settings is enough". You must verify:

1. The Argon2id variant and actual parameters.
2. RAM/CPU/latency under p95/p99 login traffic.
3. Crypto library, library version, and upgrade behavior.
4. Deployment model, memory limits, and concurrent hashing caps.
5. Interoperability with other systems and migration of old hashes.

## 7. Context-driven algorithm selection

Avoid absolute rankings. A practical decision process:

| Project condition | Option to evaluate first | Why | Remaining risks to address |
| --- | --- | --- | --- |
| New app, full control over RAM/cost, not locked to legacy protocols | Argon2id | Memory-hard; flexible parameters | Libraries, RAM for concurrency, benchmarking |
| Existing BCrypt project, many users, priority on low-disruption migration | Keep verifying BCrypt, consider gradual shift to Argon2id/SCrypt | Avoids forcing mass password resets, lowers migration risk | BCrypt cost, 72-byte limit, versioning |
| Interoperability or PBKDF2-related provider/compliance requirement | PBKDF2 with approved PRF and iterations | Broad support, easier auditing in certain ecosystems | Not memory-hard; must calibrate iterations and verify real compliance |
| Want memory-hard and project already runs SCrypt well | SCrypt | Incurs both RAM and CPU cost | N/r/p cost, Bouncy Castle, memory pressure |
| RAM-constrained servers with high authentication traffic | Benchmark BCrypt/PBKDF2 and evaluate infrastructure upgrades | Practical operational limits | Do not choose an overly weak work factor just to meet latency |
| Hash store mixes multiple algorithms/versions | `DelegatingPasswordEncoder` and gradual rehashing | Supports old hashes while swapping default encoder safely | Prefixes, unknown ids, migration state |

**Suggested decision tree:**

~~~text
Specific compliance/provider requirement?
   |-- Yes --> Verify approved algorithm + implementation
   |           (PBKDF2 is often a candidate, do not assume FIPS automatically)
   |
   |-- No --> Can allocate RAM per attempt + cap concurrency?
                 |-- Yes --> Benchmark Argon2id and SCrypt
                 |-- No --> Benchmark BCrypt/PBKDF2 at suitable cost
                              + re-evaluate infrastructure/threat model

Existing legacy hashes in database?
   |-- Yes --> Retain legacy verifier, version hashes,
   |           rehash only after successful matches or another safe flow
   |-- No --> Establish id/version policy from day one
~~~

A long, random, non-reused password still matters. No algorithm mitigates all risk if users pick leaked passwords, the login endpoint lacks rate limiting, or the application itself is compromised.

## 8. Proper benchmarking: balancing attack difficulty and availability

A sound hashing policy does not come from a "blog default". Set a latency target **with a dedicated budget** for encode/verify based on SLA and real traffic estimates. Measure at least:

- **Single-request time:** median/p95/p99 of `matches` and `encode` on representative inputs.
- **Runtime environment:** CPU instance, x86/ARM architecture, container CPU quota, JVM, GC, provider version.
- **Memory:** heap/native, allocation rate and high-watermark, concurrent attempts.
- **Throughput:** requests/second, bursts, timeouts, queueing, DoS susceptibility at login.
- **Scalability:** replica count, cloud cost, and impact on the Servlet container's thread pool.

Example: if each attempt uses 32 MiB of dedicated memory and 100 attempts actually run concurrently, that ideal budget alone is around 3,200 MiB, **excluding** heap, threads, and algorithm overhead. This is an illustrative calculation, not a fixed RAM figure for Argon2/SCrypt. With memory-hard password hashing, set **concurrent attempt limits** and test resource pressure under hostile load.

### 8.1. Measuring cost without flawed benchmarks

Simple measurement snippet for an encoder:

~~~java
long start = System.nanoTime();
boolean matched = encoder.matches(rawPassword, storedHash);
long elapsedNanos = System.nanoTime() - start;

System.out.println("verified=" + matched);
System.out.println("elapsedMillis=" + elapsedNanos / 1_000_000);
~~~

This is an **illustrative code snippet**, not a standalone program. `elapsedMillis` is not fixed; no single exact stdout can be stated across all machines. Serious benchmarking requires warm-up, many iterations, preventing compiler/JIT distortion, controlling CPU quotas, measuring multiple percentiles, and simulating concurrency. You can use JMH for microbenchmarks alongside realistic load tests.

Do not benchmark by calling `encode` once on a laptop and applying that cost to production. Never turn off strong cost in releases just because tests run slow; instead use sensible test strategies for units that do not need real crypto, while keeping integration tests that prove the configured encoder works and verifies real passwords.

### 8.2. Mitigating online attacks without downgrading password hashes

Slow hashing can also be abused to cause overload. Besides calibration, deploy:

- Tiered rate limiting by account/IP/device and credential-stuffing defenses.
- Resource pools/queues capping concurrent verification attempts.
- MFA/passkeys where appropriate, plus anomalous login detection.
- Monitoring for latency, CPU, memory, authentication failures, and retry storms.
- Error messaging policies avoiding user enumeration, avoiding distinct timing/status differences between existing and non-existing users where preventable.
- Capacity headroom for bulk password changes or gradual rehashing waves.
- HTTPS and protecting secrets in logs/traces/snapshots.

## 9. Spring Security: how to configure PasswordEncoder?

In Spring Security, `PasswordEncoder` is used by username/password providers to verify credentials. In Spring Boot Servlet apps, applications typically declare a bean:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
}
~~~

This goes inside a `@Configuration` class with `@Bean` and imports; it **does not** mean every authentication flow automatically uses that bean if you configured another custom manager/provider. Verify actual bean wiring and authentication flows.

### 9.1. DelegatingPasswordEncoder and identifier prefixes

`DelegatingPasswordEncoder` uses an algorithm identifier inside the encoded password:

~~~text
{id}encodedPassword
~~~

Examples of **format shape**, not usable hash strings for authentication:

~~~text
{bcrypt-v1}<BCrypt hash>
{pbkdf2-v1}<PBKDF2 encoded hash>
{argon2id-v1}<Argon2 encoded hash>
~~~

`idForEncode` specifies the algorithm used when **creating new hashes**, while the prefix of a **stored hash** picks the right verifier for legacy data. This enables gradual migration instead of switching algorithms and locking out all users.

### 9.2. Versioned policies: do not depend on generic short names

Example building a policy with custom ids:

~~~java
Map<String, PasswordEncoder> encoders = new HashMap<>();

encoders.put("bcrypt-v1", new BCryptPasswordEncoder(12));
encoders.put("pbkdf2-v1",
    Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8());
encoders.put("scrypt-v1",
    SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8());
encoders.put("argon2id-v1",
    Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8());

PasswordEncoder selected =
    new DelegatingPasswordEncoder("argon2id-v1", encoders);
~~~

This is a **code snippet** requiring imports for `Map, HashMap`, `PasswordEncoder`, `DelegatingPasswordEncoder`, and the concrete encoders. Versioned naming lets you change cost/PRF/Argon2 settings in the future while keeping old verifiers. Ensure the id stored in the DB is exact and there is a clear policy for legacy hashes.

Note that `argon2id-v1` here is a **custom application id**, not a standard default id from `PasswordEncoderFactories`. Verifiers only recognize a hash if the map contains that id. Do not send hashes with custom ids to another service and assume that service understands them.

### 9.3. Using the built-in factory

Spring Security also provides:

~~~java
PasswordEncoder selected =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

The factory chooses a framework default configuration (typically BCrypt as the encoder for new hashes) and registers a set of corresponding verifiers. **Always check the Spring Security version in use**: id/parameter mappings can change across releases, and defaults do not equate to an organization-approved policy.

Do not mix the two approaches: a custom application id `argon2id-v1` does not automatically exist in the factory-created map unless the application registers it appropriately.

### 9.4. Missing prefixes when upgrading from legacy

An old BCrypt hash may be stored as `$2a$...` without a `{bcrypt}` prefix. `DelegatingPasswordEncoder` cannot reliably infer the algorithm by default for all such values; it may raise a missing/unmapped id error.

Safe handling approaches:

1. Inventory existing hash formats (regex/system provenance), do not rely on guesswork.
2. Define a verifier strictly for the known legacy type; never accept plaintext or `NoOpPasswordEncoder` as a blanket fallback.
3. If the prefix can be added via a data migration **without altering hash contents**, test first on a copy of the data and have a rollback plan.
4. If runtime fallback is needed, apply it only to clearly identified legacy records, control and monitor counts; never route every unknown id through a permissive verifier.
5. After a user logs in successfully, generate a new hash under the current policy and update safely with concurrency control.
6. Track remaining legacy hash counts; schedule removal of old verifiers once eligible, never deleting them while legacy data still needs support.

### 9.5. upgradeEncoding does not upgrade passwords by itself

`PasswordEncoder.upgradeEncoding(stored)` is a signal that the encoded value should be updated under policy, for example when the algorithm id is no longer `idForEncode` or parameters are too low. It **does not** have the raw password and cannot create a new hash from the old hash alone.

A rehash-at-login workflow:

~~~text
1. User enters raw password over HTTPS
2. matches(raw, storedHash) == true
3. If upgrade needed per policy:
       newHash = currentEncoder.encode(raw)
       UPDATE users SET password_hash = newHash
       WHERE id = userId AND password_hash = oldHash
4. Continue normal login flow
~~~

The `WHERE password_hash = oldHash` condition illustrates **compare-and-swap/optimistic concurrency**: preventing overwriting a password change just saved by another request. Some flows use a version column. Rehashing and saving live in the application/persistence service or an integration like `UserDetailsPasswordService` in the appropriate DAO authentication flow; verify that the provider actually enables the upgrade path.

Never rehash when the password is wrong. Never treat the old encoded hash as a raw password to hash a second time (double-hashing), because that invents a new protocol and is not equivalent to properly rehashing from the raw password.

## 10. Runnable Java 17+ example: trying all four encoders

The Spring Boot 3.3.5 project example below is a **console application** for studying password hashing. It opens no HTTP port and contains no auth endpoints; this decouples encoder selection from Servlet security filter chain configuration. Once you understand the mechanism, you can use the same encoders in a `PasswordEncoder` bean of a Spring MVC application.

### 10.1. Project structure

~~~text
password-hash-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/hash/
    │   └── PasswordHashLabApplication.java
    └── test/java/demo/hash/
        └── PasswordHashLabApplicationTests.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'password-hash-lab'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.security:spring-security-crypto'

    // Spring Security SCrypt and Argon2 encoders require a crypto backend.
    implementation 'org.bouncycastle:bcprov-jdk18on:1.78.1'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter` provides the console application bootstrap. `spring-security-crypto` provides the `PasswordEncoder` classes to study; the program does not require `spring-boot-starter-web` or registering a `SecurityFilterChain`. Bouncy Castle supplies the primitives required by SCrypt/Argon2 in the implementation used. Real projects should let a BOM/version catalog manage tested library versions and check dependency security advisories; the version shown here provides a complete configuration example.

### 10.2. Program

File `src/main/java/demo/hash/PasswordHashLabApplication.java`:

~~~java
package demo.hash;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.security.crypto.scrypt.SCryptPasswordEncoder;

@SpringBootApplication
public class PasswordHashLabApplication implements CommandLineRunner {

    public static void main(String[] args) {
        SpringApplication.run(PasswordHashLabApplication.class, args);
    }

    static Map<String, PasswordEncoder> encoders() {
        Map<String, PasswordEncoder> result = new LinkedHashMap<>();

        result.put("BCrypt", new BCryptPasswordEncoder(12));
        result.put("PBKDF2",
            Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8());
        result.put("SCrypt",
            SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8());
        result.put("Argon2",
            Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8());

        return result;
    }

    @Override
    public void run(String... args) {
        String raw = "correct-horse-battery-staple";

        encoders().forEach((name, encoder) -> {
            String hash = encoder.encode(raw);
            boolean valid = encoder.matches(raw, hash);
            boolean invalid = encoder.matches("definitely-wrong", hash);

            System.out.println(name + ": correct=" + valid
                + ", wrong=" + invalid);
        });
    }
}
~~~

With the class and project above, the **stdout produced by `System.out.println` itself** in `LinkedHashMap` order is:

~~~text
BCrypt: correct=true, wrong=false
PBKDF2: correct=true, wrong=false
SCrypt: correct=true, wrong=false
Argon2: correct=true, wrong=false
~~~

Spring Boot may print an additional banner/startup logs; therefore this stdout listing **does not** claim the entire console has only four lines. Actual hashes are not printed because random salts change the string every run, and encoded passwords should not be logged in production.

### 10.3. Tests to verify each encoder

File `src/test/java/demo/hash/PasswordHashLabApplicationTests.java`:

~~~java
package demo.hash;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordHashLabApplicationTests {

    @Test
    void allEncodersAcceptCorrectAndRejectIncorrectPasswords() {
        PasswordHashLabApplication.encoders().forEach((name, encoder) -> {
            String hash = encoder.encode("demo-password");

            assertNotNull(hash, name);
            assertTrue(encoder.matches("demo-password", hash), name);
            assertFalse(encoder.matches("wrong-password", hash), name);
        });
    }

    @Test
    void encodedValueIsNotPlaintext() {
        PasswordEncoder encoder =
            PasswordHashLabApplication.encoders().get("BCrypt");

        String hash = encoder.encode("demo-password");

        assertFalse("demo-password".equals(hash));
        assertTrue(encoder.matches("demo-password", hash));
    }
}
~~~

These two tests verify the `encode/matches` contract without comparing hashes to a fixed value. Even if algorithm parameters change, these baseline tests remain valid. To verify migrations, add tests for multiple ids/versions according to §DelegatingPasswordEncoder§ and known legacy hash fixtures.

### 10.4. Running

In the project directory, if a compatible Gradle installation is present:

~~~bash
gradle test
gradle bootRun
~~~

If a Gradle wrapper is present, prefer:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows, use `gradlew.bat test` and `gradlew.bat bootRun`. The Spring Boot program requires dependency classpaths; plain `javac`/`java` cannot run without the JARs. Hashing operations can take noticeable time depending on parameters/hardware; do not use local run times to conclude which algorithm is best.

## 11. Deployment policy example: DelegatingPasswordEncoder bean

In a real Servlet application, you can declare a single bean for username/password providers to use:

~~~java
package demo.security;

import java.util.HashMap;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.scrypt.SCryptPasswordEncoder;

@Configuration
public class PasswordPolicyConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        Map<String, PasswordEncoder> verifiers = new HashMap<>();

        verifiers.put("bcrypt-2026",
            new BCryptPasswordEncoder(12));
        verifiers.put("pbkdf2-2026",
            Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8());
        verifiers.put("scrypt-2026",
            SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8());
        verifiers.put("argon2id-2026",
            Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8());

        return new DelegatingPasswordEncoder(
            "argon2id-2026", verifiers);
    }
}
~~~

This is a **Spring configuration class for use inside an application that already has the required dependencies**, not a standalone runnable app. For production use, customize ids per policy and configure **benchmarked** parameters; this code only illustrates supporting multiple algorithms/versions and using Argon2id for new hashes.

### 11.1. Registration path

~~~java
String rawPassword = registrationRequest.password();
String encoded = passwordEncoder.encode(rawPassword);
// Only store encoded in the database.
~~~

This is an illustrative snippet; `registrationRequest`, `passwordEncoder`, and the persistence layer are provided by the application. The encoded password carries the new policy's prefix. Never store plaintext in event logs, request traces, telemetry, or an auxiliary "debug" column.

### 11.2. Login path

~~~java
boolean valid =
    passwordEncoder.matches(rawPasswordFromLogin, storedHash);
~~~

This is a snippet; actual authentication code in Spring Security normally resides in the appropriate provider, so you do not need to call `matches` manually in a controller when using the right provider. With `DelegatingPasswordEncoder`, the verifier is chosen by the id in the stored hash; only a true result can lead to successful `Authentication`.

### 11.3. Algorithm transition roadmap across versions

Suppose the database stores:

~~~text
{bcrypt-2026}$2a$...             -> still verified by bcrypt-2026
{pbkdf2-2026}<PBKDF2 data>       -> still verified by pbkdf2-2026
{argon2id-2026}<Argon2 data>     -> new hash under current policy
~~~

The strings above are **format notation**, not hashes usable with `matches`. An application might in the future introduce `argon2id-2028` with different cost settings, keep `argon2id-2026` as a verifier for old data, and gradually rehash when users log in successfully.

This versioning solves two problems:

1. **Switching algorithms** from BCrypt/PBKDF2/SCrypt to Argon2id without locking out existing users.
2. **Changing parameters** of the same algorithm after benchmarking while still cleanly identifying the matching verifier.

Do not retire old verifiers too early; infrequent users can hold legacy hashes for years. Consider a password reset policy for accounts that cannot migrate passively and pose high risk, while evaluating user-experience impact.

## 12. Real-world scenarios and common pitfalls

### 12.1. Already on BCrypt—must we convert everything to Argon2 immediately?

Not necessarily. First confirm the current cost, active hash inventory, accounts with weak/leaked passwords, online protections, and production budget. A practical plan could be:

- Retain a safe BCrypt verifier for old hashes.
- Benchmark Argon2id with deliberate memory/time settings.
- Configure a `DelegatingPasswordEncoder` policy with the new id.
- Migrate hashes after successful login using the raw password available during authentication.
- Monitor latency, error rates, and remaining legacy counts.
- Remove legacy verifiers once no supported records remain or a valid reset policy covers them.

### 12.2. Leaving all encoders on default settings then benchmarking time

Saying "algorithm A is stronger than B" is invalid if the defaults represent vastly different costs. Set a **latency/RAM budget**, select and measure candidate configurations within that budget, and compare attack costs based on each algorithm's properties. If the organization requires higher resistance, adjust the infrastructure budget as well.

### 12.3. Using the same salt for every account for easier testing

This is an anti-pattern. Salt must be generated randomly and uniquely per password; never fix a salt just for "predictable" hash outputs. Tests should check `matches` and valid formatting rather than asserting an encoded value equals a constant string.

### 12.4. Adding a pepper but storing it in the same database as the hash

That largely defeats secret separation. If used, a pepper must be protected independently, versioned, and have a rotation and recovery plan; losing the pepper can make pepper-dependent hashes unverifiable. Do not add a pepper without an operational design first.

### 12.5. Using NoOpPasswordEncoder to fix legacy prefix errors

`NoOpPasswordEncoder` does not hash passwords; setting it as the default fallback for prefix-less hashes can create a severe vulnerability. Legacy data without an id must be handled via **known formats and verified migrations**, not by lowering security standards.

### 12.6. Using BCrypt with very long Unicode passwords without checking byte length

BCrypt's ~72-byte limit is easy to overlook. If the application permits long passwords, establish a clear byte-encoding policy, test inputs past the limit, and plan migrations. Inconsistent Unicode normalization changes can prevent old passwords from logging in. Never apply trim/lowercase to passwords as you would to usernames.

### 12.7. Changing PBKDF2 PRF/iterations without tracking versions

Old hashes can become unverifiable or checked with wrong parameters. Package versions/mappings cleanly and retain old profiles until no records remain that need verification.

### 12.8. Memory-hard improves security yet crashes the system on traffic spikes

Argon2id/SCrypt protect better under certain threat models by requiring RAM, but you must cap concurrent hashing, measure peak memory, and guard the endpoint against untrusted traffic. Never let unbounded login requests independently claim memory solely because each password uses a strong algorithm.

### 12.9. Assuming PasswordEncoder replaces the entire auth architecture

No. `PasswordEncoder` only verifies passwords; authorization, account status, user lockouts, MFA, tokens/sessions, CSRF, HTTPS, and rate limiting are separate layers. In Spring Security Servlet, proper integration of `AuthenticationProvider`, `UserDetailsService`, `AuthenticationManager`, and `SecurityFilterChain` must still be ensured.

### 12.10. Thinking BCrypt/Argon2 work like symmetric encryption that can be decrypted

Password KDFs are one-way functions. Never store an AES key beside password hashes to "decrypt when a user forgets"; the proper design is password reset via a secure flow and a new hash.

## 13. Practice exercises

1. Explain why `PasswordEncoder.matches(raw, encoded)` must never be replaced with `encode(raw).equals(encoded)`.
2. Given a system storing 500,000 bcrypt hashes, plan a migration to Argon2id without requiring concurrent user logins and without breaking inactive accounts.
3. Distinguish **CPU-hard** from **memory-hard**. Why does SCrypt/Argon2id's RAM requirement make large-scale offline attacks costlier, yet expose the login endpoint to DoS pressure?
4. Choose among BCrypt/PBKDF2/SCrypt/Argon2id for three contexts: (a) a Java backend needing broad compatibility, (b) an organization bound by specific compliance/provider rules, (c) a new service with RAM budget and benchmarking capability. Explain the extra conditions rather than only naming the algorithm.
5. Design a benchmark with warm-up, p50/p95/p99, throughput, concurrency, and a memory budget; explain why a single `System.nanoTime` call should not drive the final decision.
6. Write a test verifying `PasswordEncoderFactories.createDelegatingPasswordEncoder()` produces a hash with the expected id for your framework version without hardcoding the output hash.
7. For legacy BCrypt hashes lacking a prefix, propose a safe migration. Why is a fallback of "all prefix-less hashes use NoOp" dangerous?
8. Explain the difference between `upgradeEncoding(storedHash)` and actually updating the DB. Design a concurrency-safe SQL update.
9. For BCrypt, explain why the ~72-**byte** limit makes multi-byte Unicode strings prone to subtle issues.
10. If the current policy is `argon2id-2026` while the database still holds `pbkdf2-2026`, how should updates work after successful `matches`? What happens if the user changes their password concurrently?
11. If an application leaks its password hash database while the login API has very strict rate limiting, why must offline attacks still be considered?
12. When using SCrypt or Argon2, how do you choose a concurrent hash attempt cap based on actual RAM limits and CPU quotas?
13. Describe how to store and rotate a pepper if required by the organization, distinguishing it from the salt packaged inside the hash.

## 14. Checklist for choosing and operating password hashing

- [ ] Threat model covers both database breach/offline cracking and online credential stuffing.
- [ ] Only proper password hashing/KDFs are used—never plain MD5/SHA-256 or plaintext.
- [ ] Every password has an encoder-generated random salt; never reuse a fixed salt.
- [ ] Algorithm and parameters are **benchmarked on real infrastructure** and scheduled for periodic review.
- [ ] For memory-hard algorithms, account for RAM/concurrency and enforce resource limits.
- [ ] If compliance applies, verify the certified provider/certification, not just the algorithm name.
- [ ] Password policy handles Unicode/length consistently; note BCrypt's byte limit.
- [ ] Use `PasswordEncoder.matches`, never re-encode and compare hash strings.
- [ ] Hashes are stored with an **algorithm/version id** when supporting multiple profiles.
- [ ] Legacy formats have scoped verifiers; unknown ids/malformed hashes fail closed.
- [ ] Have a plan for rehash after successful login, safe DB updates, and migration monitoring.
- [ ] Never log raw passwords, tokens, peppers, or encoded hashes indiscriminately.
- [ ] Login has rate limiting, monitoring, HTTPS, MFA when appropriate, and error handling preventing user enumeration.
- [ ] Spring Security Servlet code injects `PasswordEncoder` properly into the active provider/manager.
- [ ] Unit tests cover `encode/matches`, integration tests cover authentication, and tests verify migration.
- [ ] Have a rollback/version compatibility plan when changing algorithms or cost.

**Conclusion:** BCrypt is a pragmatic and widely adopted choice; PBKDF2 offers compatibility advantages and can suit standard/provider rules; SCrypt and Argon2id are strong memory-hard candidates to raise offline attack costs. **The best algorithm in production is the one properly configured, benchmarked, versioned, monitored, and upgraded for that product's threat model.** In Spring Security, `PasswordEncoder` and `DelegatingPasswordEncoder` turn this decision into an implementation policy that can evolve over time.
