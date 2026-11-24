# SCryptPasswordEncoder, Argon2PasswordEncoder, and Memory Cost

> **Context:** Spring Security — Authentication → **Password Hashing**. This lesson clarifies how `SCryptPasswordEncoder` and `Argon2PasswordEncoder` generate/verify passwords using *memory-hard* algorithms, the meaning of cost parameters, how to estimate **memory per check and under multiple concurrent requests**, choosing parameters based on real resources, and safe deployment/migration with Spring Security. The standalone example uses Java 17, Spring Security 6.5.11, and Bouncy Castle 1.86.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain why plaintext passwords must not be stored, why standalone SHA-256 must not be used for passwords, and why hashes are not decryptable encryption.
2. Distinguish `encode(rawPassword)`, `matches(rawPassword, encodedPassword)`, random salt, work factor parameters, and `upgradeEncoding(...)` on `PasswordEncoder`.
3. Understand scrypt with `N`, `r`, `p`, `dkLen`, and `saltLength`; estimate core memory via `128 × N × r` bytes.
4. Understand Argon2id with `m` (KiB), `t` (iterations), `p` (parallelism), salt/hash sizes; know that `m` is the **total** memory for one hash operation, without multiplying `m` by `p`.
5. Distinguish **algorithmic memory-hardness** from **actual JVM heap/RSS**, concurrency impact, GC, container limits, and login rate limiting.
6. Run a Java 17 program verifying success/failure with both encoders, using `DelegatingPasswordEncoder` to distinguish formats, and reading memory-estimation outputs.
7. Design strategies for benchmarking, thread/concurrency management, DoS prevention, and upgrading parameters/algorithms for a running system.

## 2. Why Do We Need Adaptive, Memory-Hard Password Hashing?

Suppose a database stores passwords. If stored in plaintext, losing the database immediately reveals all passwords. If using a fast hash such as `SHA-256(password)`, an attacker can test huge numbers of passwords per second using GPUs/ASICs. Adding a random salt prevents multiple users from sharing identical hashes or using precomputed lookup tables, **yet a fast hash function is still insufficient against offline guessing**.

A suitable password hashing function must provide:

- **One-way transformation:** output cannot be "decrypted" to recover the original password by design.
- **Unique random salt per record:** two calls to `encode("same-password")` usually differ; salt does not need to be secret, but must be stored with the encoded hash or in a compatible format.
- **Adaptive work factor:** `matches` is resource-intensive enough to slow down offline guessing while remaining practical for legitimate traffic.
- **Memory hardness (for scrypt/Argon2):** a single attempt requires substantial memory, disadvantaging hardware optimized for high-density parallel trials.
- **Stable format and versioning:** you must know the algorithm/parameters of legacy hashes so they remain verifiable during upgrades.

**Scrypt** was designed to force bulk hash computation to consume substantial RAM. **Argon2** is the algorithm family that won the Password Hashing Competition; the **Argon2id** variant combines properties of Argon2i/Argon2d and is a widely favored choice for password hashing. Spring Security provides encoders for both scrypt and Argon2.

Common point of confusion: a password hash containing salt and parameters is **not an access token**, **not an encryption key**, and **not proof that a user is logged in**. It is solely data used to verify a password when an actual authentication attempt occurs.

## 3. PasswordEncoder Contract in Spring Security

Main methods:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

This is a **conceptual signature** for learning the API; library source code may include nullability annotations and concrete implementations. Individual encoders supply their own storage formats while implementing this core contract.

| API | Input | What It Does | What It Does Not Do |
| --- | --- | --- | --- |
| `encode(...)` | Raw password from a trusted registration/reset flow | Produces an adaptive hash with salt/parameters | Does not create `Authentication` or auto-save to DB |
| `matches(...)` | User-submitted password and stored hash | Computes/verifies per hash metadata | Does not check locked, enabled, roles, or MFA |
| `upgradeEncoding(...)` | Stored hash | Indicates whether hash regeneration may be needed per encoder policy | Does not automatically modify DB records |
| `PasswordEncoderFactories.createDelegatingPasswordEncoder()` | None | Creates a multi-format encoder with the framework's default encode algorithm | Does not mean all new passwords default to scrypt/Argon2 |

Correct verification example:

~~~java
String stored = passwordEncoder.encode("example-secret");
boolean accepted = passwordEncoder.matches("example-secret", stored);
~~~

**Do not compare `encode(input).equals(stored)`:** two `encode` calls usually generate different salts and thus produce different hash strings. Instead of comparing two new hashes, `matches` reads the salt and parameters from the old hash and computes verification against it.

**Never write a custom `PasswordEncoder` that always returns true** for users found in cache. Account caching and password verification are two separate responsibilities.

## 4. SCryptPasswordEncoder: N, r, p, and Memory Estimation

### 4.1. Creating the Encoder with the Official Preset

~~~java
import org.springframework.security.crypto.scrypt.SCryptPasswordEncoder;

SCryptPasswordEncoder encoder =
        SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8();
~~~

Per Spring Security 6.5 Javadoc, the `defaultsForSpringSecurity_v5_8()` preset uses:

| Parameter | Value | Meaning |
| --- | ---: | --- |
| `cpuCost`, scrypt notation `N` | `65_536` = `2^16` | CPU/memory cost parameter; must be a valid power of 2 |
| `memoryCost`, notation `r` | `8` | Scrypt block size parameter; **not directly 8 MiB** |
| `parallelization`, notation `p` | `1` | Parallelism / mixing thread count per algorithm definition |
| `keyLength` / `dkLen` | `32` bytes | Output key/hash length |
| `saltLength` | `16` bytes | Random salt length |

The names `cpuCost` and `memoryCost` are **Spring constructor parameter names**, whereas the standard algorithm symbols are usually `N` and `r`. Do not interpret `memoryCost=8` as allocating only 8 MB. Main memory must be calculated from `N` and `r`.

Explicit initialization with the same parameters:

~~~java
SCryptPasswordEncoder scrypt =
        new SCryptPasswordEncoder(
                1 << 16, // N
                8,       // r
                1,       // p
                32,      // dkLen
                16);     // saltLength (bytes)
~~~

When tuning parameters, verify both the implementation's valid constraints and real runtime/memory on your target environment. Do not pick an arbitrary `N` that is not a power of 2; nor assume increasing `p` linearly increases security across all configurations.

### 4.2. Core Memory Estimation Formula

For scrypt, the estimate for the algorithm's large working table is:

\[
M_{\text{scrypt,base}} \approx 128 \times N \times r\quad\text{bytes}
\]

Substituting the preset:

\[
128 \times 65\,536 \times 8
= 67\,108\,864\ \text{bytes}
= 64\ \text{MiB}.
\]

**64 MiB is the estimated core memory size of scrypt for a single computation**, not a promise that JVM heap grows by exactly 64 MiB, not a measured RSS value, and not inclusive of all buffers/structures/library overhead.

Related parameters:
- Increasing `N` generally increases both CPU and core memory.
- Increasing `r` increases core memory and computational cost.
- Increasing `p` affects block count/computational load and may have extra memory impact, though you must not use the wrong formula `128 × N × r × p` as a general claim about the main memory table across implementations.
- `dkLen` is the output length (32 bytes in the preset), **not** the RAM required for computation.

### 4.3. Scrypt Level Examples to Understand Scaling

Holding `r=8` and `p=1`:

| N | `128 × N × r` | Estimated Size |
| ---: | ---: | ---: |
| `2^14` = 16,384 | 16,777,216 bytes | 16 MiB |
| `2^15` = 32,768 | 33,554,432 bytes | 32 MiB |
| `2^16` = 65,536 | 67,108,864 bytes | 64 MiB |
| `2^17` = 131,072 | 134,217,728 bytes | 128 MiB |

This is a **theoretical calculation**, not a latency benchmark or a universal minimum parameter standard for every machine. Doubling `N` roughly doubles the main memory table, while measured latency also depends on CPU architecture, RAM bandwidth, Bouncy Castle/Spring Security versions, GC, and concurrency.

## 5. Argon2PasswordEncoder: memory, iterations, parallelism

### 5.1. Spring Security Preset

~~~java
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;

Argon2PasswordEncoder encoder =
        Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();
~~~

Per Spring Security 6.5 Javadoc, this preset initializes:

~~~java
Argon2PasswordEncoder argon2 =
        new Argon2PasswordEncoder(
                16,       // saltLength (bytes)
                32,       // hashLength (bytes)
                1,        // parallelism (p)
                1 << 14,  // memory (KiB)
                2);       // iterations (t)
~~~

| Parameter | Value | Meaning |
| --- | ---: | --- |
| `saltLength` | 16 bytes | Random salt length |
| `hashLength` | 32 bytes | Hash length |
| `parallelism` = `p` | 1 | Number of lanes per algorithm |
| `memory` = `m` | 16,384 KiB | Total configured memory for one Argon2 operation |
| `iterations` = `t` | 2 | Number of passes/iterations per algorithm |

**Correct unit conversion:** `16_384 KiB / 1_024 = 16 MiB`. In this Java constructor, `memory` is neither "16,384 bytes" nor "16,384 MiB". Wrong units can produce an overly weak configuration or cause memory overload.

### 5.2. Which Parameter Affects What?

- **`memory`/`m`:** sets the algorithmic memory budget in KiB. Raising `m` costs attackers more memory, yet the application must also have sufficient RAM.
- **`iterations`/`t`:** increases computation passes. Usually increases latency without simply multiplying peak memory by `t`; `t` is the pass count, not "t copies of RAM".
- **`parallelism`/`p`:** describes lane count; **`m` is total memory**, not `m` KiB per lane. Some runtimes optimize multi-threading, while the Bouncy Castle-based Spring Security implementation currently notes **not exploiting parallelism/optimizations in the way an attacker might**.
- **`saltLength` and `hashLength`:** configure salt/hash sizes; they do not replace the work factor.

A good property of Argon2id encoded hashes is that the format records algorithmic parameters such as `m`, `t`, `p` along with salt and hash in a compatible format. **Never fabricate strings or edit parameters inside an encoded hash manually**; `matches` requires the exact format emitted by the implementation and the original salt.

### 5.3. Understanding Memory Calculation Correctly

The Argon2 default above is **16 MiB per operation per parameter m**. When `p` is greater than 1, do not infer base memory as `m × p`; memory is partitioned across lanes by the algorithm. However, **concurrent authentication requests** are independent operations and **can** cause RAM demand to grow nearly linearly with the number of hashes running simultaneously.

Example with 8 concurrent verify requests:
- Scrypt with 64 MiB main table/request → roughly **512 MiB** before overhead.
- Argon2 with `m=16 MiB`/request → roughly **128 MiB** before overhead.

This is not a guarantee that Argon2 always uses less RAM or is safer than scrypt in every configuration: **the two framework presets simply use different parameters**. Evaluating algorithms requires comparing on identical hardware, latency thresholds, threat models, and valid resource budgets.

## 6. SCrypt vs. Argon2: Comparison by Practical Questions

| Criterion | SCryptPasswordEncoder | Argon2PasswordEncoder |
| --- | --- | --- |
| Algorithm | scrypt | Argon2 (typically Argon2id format) |
| v5_8 preset | `N=65536,r=8,p=1` | `m=16384 KiB,t=2,p=1` |
| Base memory per preset | ≈64 MiB | 16 MiB |
| Cost tuning | `N`, `r`, `p` | `m`, `t`, `p` |
| Preset salt/hash length | Salt 16 B, derived key 32 B | Salt 16 B, hash 32 B |
| JVM characteristics | Large memory tables and buffers, affected by GC/heap | Bouncy Castle, requires dependency, notes on parallel optimization |
| Stored output | Hash containing metadata/salt in Spring's scrypt format | Hash containing Argon2 metadata/salt |
| Common API | `encode`, `matches`, `upgradeEncoding` | `encode`, `matches`, `upgradeEncoding` |
| Works with DelegatingPasswordEncoder | Yes | Yes |
| Makes account authenticated by itself? | No | No |

### When Should You Choose Which Algorithm?

There is no rule to "always pick whichever has more MiB per call". Evaluate:

1. **Security/compliance policy:** organizational approval of the algorithm, actively supported libraries with security patches.
2. **Threat model:** resisting offline guessing if hashes leak; random salts, rate limiting, and password policies are still required.
3. **Server budget:** memory/concurrency, container quotas, login latency limits, node scaling headroom.
4. **Actual implementation:** Argon2 on Bouncy Castle has different optimization characteristics from native libraries; benchmark in the target runtime environment.
5. **Migration capability:** databases containing existing bcrypt/scrypt/Argon2/PBKDF2 hashes that must still verify during transitions.
6. **Product lifecycle:** policies for raising cost factors over time and upgrading hashes when users log in successfully.

Spring Security presets provide **starting points**, not replacements for benchmarking. Password storage documentation suggests tuning a single verification to roughly **1 second** on the target machine as a reference guideline; this is **not a mandatory SLA**. High-traffic or tightly memory-constrained services must also balance concurrency and UX.

## 7. Memory Under Concurrent Requests: What Many Applications Miss

### 7.1. From One Hash to Many Concurrent Logins

Suppose each scrypt verification uses an estimated 64 MiB large working region. If 8 verifications are in their peak memory phase concurrently, the working tables alone can reach around:

\[
8 \times 64\ \text{MiB} = 512\ \text{MiB}.
\]

With 32 concurrent verifications, the estimate reaches **2 GiB**, before counting application object heap, thread stacks, HTTP buffers, JVM code cache, off-heap/direct buffers, user caches, and other libraries.

With Argon2 `m=16 MiB` and 32 concurrent requests, algorithmic working memory is roughly **512 MiB**. That does not mean the system can automatically run 4× more logins at this setting; latency, CPU, RAM bandwidth, and optimization differences also affect throughput.

### 7.2. Quick Estimation Table (Not Measured Numbers)

| Active concurrent hashes | Scrypt v5_8 (64 MiB base) | Argon2 v5_8 (16 MiB base) |
| ---: | ---: | ---: |
| 1 | 64 MiB | 16 MiB |
| 2 | 128 MiB | 32 MiB |
| 4 | 256 MiB | 64 MiB |
| 8 | 512 MiB | 128 MiB |
| 16 | 1,024 MiB (1 GiB) | 256 MiB |
| 32 | 2,048 MiB (2 GiB) | 512 MiB |

This formula estimates **simultaneously executing hash operations**, not "open connections" and not "online users". Having 10,000 users with active sessions does not mean the server holds 10,000 active hash memory regions.

### 7.3. Heap, Off-Heap, RSS, and Container Limits

- **JVM heap:** memory for Java objects managed by GC. Many implementations allocate large arrays on the heap; monitor allocation rate and peak heap.
- **Native/off-heap:** other components or algorithms/implementations may use memory outside the heap; do not assume `-Xmx` equals total RSS.
- **RSS (resident set size):** the process's resident RAM; impacted by live heap, off-heap, thread stacks, and shared mappings.
- **Container memory limit:** cgroups/containers cap the entire process; the JVM may hit OOM/GC pressure or the container may be OOM-killed before the app can return an error.
- **GC pauses/CPU bandwidth:** not just RAM; password hashing can contend for CPU/cache/RAM bandwidth with the application's own database and client requests.

Therefore, never treat the "64 MiB × concurrency" table as final capacity sizing. It is an **early warning**. Measure on the actual JVM runtime, image, CPU architecture, and container limits, paired with safely bounded load tests.

### 7.4. Resource Budget Example

Suppose an instance has a 1 GiB memory limit; after reserving space for application heap, buffers, and operational safety, suppose the net budget for password verification is only **256 MiB**. Using the 64 MiB/scrypt base estimate, **4 concurrent operations already consume the entire 256 MiB**, *before counting overhead*.

Do not configure "max concurrent=4" merely because division equals the budget. You need **headroom** for overhead, variance, GC, retries, and unrelated requests; start with a lower limit and benchmark. These numbers illustrate a sizing exercise, not a fixed recommendation for every service.

## 8. Runnable Java 17 Demo: Comparing encode/matches and Computing Memory Budget

This demo uses only Spring Security Crypto and Bouncy Castle, **with no Spring MVC/Boot needed**. It computes real hashes with both encoders (no algorithm simulation) and prints **booleans/theoretical memory estimates**, without printing passwords/hashes.

### 8.1. Directory Structure

~~~text
password-memory-lab/
├── settings.gradle
├── build.gradle
└── src/main/java/example/passwordcost/
    └── PasswordMemoryLab.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'password-memory-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
    implementation 'org.bouncycastle:bcprov-jdk18on:1.86'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.passwordcost.PasswordMemoryLab'
}
~~~

**Why add Bouncy Castle?** Spring Security's `Argon2PasswordEncoder` currently relies on this library. Without the dependency, applications can hit `NoClassDefFoundError` during `encode`/`matches`. The Bouncy Castle version shown here is for the example; real environments must check advisories/BOMs and update compatible patches as released.

### 8.2. Complete Java File

`src/main/java/example/passwordcost/PasswordMemoryLab.java`:

~~~java
package example.passwordcost;

import java.util.Map;

import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.scrypt.SCryptPasswordEncoder;

public class PasswordMemoryLab {

    public static void main(String[] args) {
        // Dummy password used only in local experiments.
        String rawPassword = "demo-password!";

        SCryptPasswordEncoder scrypt =
                SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8();
        Argon2PasswordEncoder argon2 =
                Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();

        // Do not print salt/hash since each encode call generates a random salt.
        String scryptHash = scrypt.encode(rawPassword);
        String argon2Hash = argon2.encode(rawPassword);

        System.out.println("scrypt-correct="
                + scrypt.matches(rawPassword, scryptHash));
        System.out.println("scrypt-wrong="
                + scrypt.matches("wrong-password", scryptHash));

        System.out.println("argon2-correct="
                + argon2.matches(rawPassword, argon2Hash));
        System.out.println("argon2-wrong="
                + argon2.matches("wrong-password", argon2Hash));

        // Estimates the algorithm's large memory region, NOT measured RSS/heap.
        long scryptBaseBytes = 128L * (1 << 16) * 8;
        long scryptBaseMiB = scryptBaseBytes / (1024 * 1024);
        long argon2BaseKiB = 1L << 14;
        long argon2BaseMiB = argon2BaseKiB / 1024;

        System.out.println("scrypt-base-mib=" + scryptBaseMiB);
        System.out.println("argon2-base-mib=" + argon2BaseMiB);

        int simultaneous = 8;
        System.out.println("scrypt-8-base-mib="
                + (simultaneous * scryptBaseMiB));
        System.out.println("argon2-8-base-mib="
                + (simultaneous * argon2BaseMiB));

        // Demo-defined IDs: real apps must maintain compatible mappings
        // for all previously stored hashes.
        PasswordEncoder delegating = new DelegatingPasswordEncoder(
                "argon2-v58",
                Map.of(
                        "argon2-v58", argon2,
                        "scrypt-v58", scrypt));

        String newlyEncoded = delegating.encode(rawPassword);
        String storedScrypt = "{scrypt-v58}" + scryptHash;

        System.out.println("current-id-match="
                + delegating.matches(rawPassword, newlyEncoded));
        System.out.println("old-id-match="
                + delegating.matches(rawPassword, storedScrypt));
        System.out.println("old-id-upgrade="
                + delegating.upgradeEncoding(storedScrypt));
    }
}
~~~

### 8.3. Test Run

From `password-memory-lab` with JDK 17+ and a compatible Gradle or Gradle Wrapper:

~~~bash
gradle run --quiet
~~~

If a wrapper exists:

~~~bash
./gradlew run --quiet
~~~

On Windows PowerShell, use `.\gradlew.bat run --quiet`.

**Output from `System.out.println`** (excluding Gradle or library messages):

~~~text
scrypt-correct=true
scrypt-wrong=false
argon2-correct=true
argon2-wrong=false
scrypt-base-mib=64
argon2-base-mib=16
scrypt-8-base-mib=512
argon2-8-base-mib=128
current-id-match=true
old-id-match=true
old-id-upgrade=true
~~~

**Why is the boolean output deterministic?** Random salts make the hash strings vary each time, yet `matches` reads the matching salt/metadata from each hash so the result is true for the right password and false for the wrong password. `DelegatingPasswordEncoder` retains both IDs to verify old hashes; when `idForEncode` is `argon2-v58`, the entry with ID `scrypt-v58` is flagged as needing an upgrade.

**Do not misunderstand the "memory" lines:** the `base-mib` lines calculate exact preset parameters with Java arithmetic; **they do not measure peak heap, RSS, or execution time**. They do not prove by themselves that your system has enough resources to run 8 hashes concurrently.

### 8.4. Parameter-Increase Variant (Integration Snippet)

Replace presets with explicit configurations once benchmarked and policy-checked:

~~~java
SCryptPasswordEncoder strongerScrypt =
        new SCryptPasswordEncoder(
                1 << 17, 8, 1, 32, 16); // 128 MiB base

Argon2PasswordEncoder strongerArgon2 =
        new Argon2PasswordEncoder(
                16, 32, 1, 1 << 16, 3); // m=64 MiB, t=3
~~~

**This is only a variant illustrating parameters**, not a universal "recommended" setting. Raising costs can push the application into OOM under login load, especially in small containers. Before production use, measure latency, peak memory, throughput, and stress behavior; also create an appropriate upgrade path for legacy hashes.

## 9. Integrating into Spring Boot and DaoAuthenticationProvider

For database-stored accounts, `DaoAuthenticationProvider` uses `UserDetailsService` to load the user and `PasswordEncoder.matches(...)` to compare the submitted password against the stored hash. The provider returns a successful `Authentication` only if both credential verification and account status checks succeed.

Flow:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as Authentication Filter
    participant M as AuthenticationManager
    participant P as DaoAuthenticationProvider
    participant U as UserDetailsService
    participant E as PasswordEncoder
    C->>F: Username + password over HTTPS
    F->>M: Unauthenticated Authentication
    M->>P: authenticate(request)
    P->>U: loadUserByUsername(username)
    U-->>P: UserDetails + encodedPassword
    P->>E: matches(raw, encoded)
    alt Valid evidence and account status
        E-->>P: true
        P-->>M: Authenticated Authentication
    else Invalid evidence / disallowed account
        E-->>P: false or status check failed
        P-->>M: AuthenticationException
    end
~~~

Conceptual configuration when wanting scrypt for new passwords:

~~~java
// In a Spring Boot @Configuration class, import @Bean accordingly.
@Bean
PasswordEncoder passwordEncoder() {
    return SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8();
}
~~~

Or Argon2:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();
}
~~~

These two snippets are **configuration alternatives**, not to be declared together with the same type without specifying `@Primary`/`@Qualifier`. Applications already storing multiple hash algorithms usually need `DelegatingPasswordEncoder` with ID mappings rather than swapping the bean directly and breaking legacy logins.

**Note:** hashes must be created on the registration/reset/password-change path and stored in the DB with necessary metadata. `UserDetailsService` reads the exact encoded value from the DB; never re-hash an already hashed password when loading a user. During authentication, never apply `encode(raw) == storedHash`; use `matches`.

## 10. DelegatingPasswordEncoder and Upgrading Without Locking Out Legacy Accounts

### 10.1. Why Preserve Algorithm IDs?

A system may already store bcrypt, older-parameter scrypt, and multiple versions of Argon2. Standard format when using `DelegatingPasswordEncoder`:

~~~text
{id}encodedPassword
~~~

Application-defined examples:

~~~text
{scrypt-v58}<valid-scrypt-hash>
{argon2-v58}<valid-argon2-hash>
~~~

`idForEncode` determines the algorithm **for new passwords**; other IDs in the map allow **verifying old hashes**. `DelegatingPasswordEncoder` does not automatically know custom IDs unless the application defines the corresponding mapping. Names like `scrypt-v58` and `argon2-v58` in the demo are **custom IDs**, not Spring Security defaults.

**Specifically regarding the default factory:**

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` typically selects `bcrypt` for new encodings in Spring Security 6.5, even though the factory also maps many other encoders. Spring Security's registered mappings include older IDs like `scrypt`/`argon2` and newer preset IDs like `scrypt@SpringSecurity_v5_8` / `argon2@SpringSecurity_v5_8`. **Do not assume that merely changing the bean from bcrypt to Argon2 lets old bcrypt hashes verify automatically** if a compatible encoder is no longer registered.

### 10.2. Migration on Successful Login

A gradual upgrade pattern:

~~~text
1. Store hashes with algorithm ID/version.
2. User submits password over a secure login channel.
3. DelegatingPasswordEncoder.matches(raw, storedHash).
4. If valid and upgradeEncoding(storedHash) == true:
   - encode(raw) with the current policy;
   - update DB with version check / old-hash comparison to prevent races;
   - never store/log raw password;
   - ensure proper transaction and auditing.
5. Complete authentication via Spring Security's mechanism.
~~~

In Spring Security, `DaoAuthenticationProvider` supports integrated hash upgrades via `UserDetailsPasswordService` when configured; that is a cleaner place than copying raw passwords into controllers or async queues. If the application does not regularly use username/password logins (OIDC, passkeys), plan a separate migration strategy for rarely used accounts.

**Upgrading does not mean resetting the password:** the new hash can be created from the same raw password right after it is verified at login; you cannot accurately convert an old bcrypt/scrypt hash to Argon2 without the raw password or a valid reset flow.

### 10.3. Do Not Permit Dangerous Fallbacks

When `DelegatingPasswordEncoder` encounters an unrecognized ID or a missing prefix, by default it can throw `IllegalArgumentException`. Do not work around that with `setDefaultPasswordEncoderForMatches(NoOpPasswordEncoder.getInstance())` in production: that can turn unknown-format data into a plaintext password comparison path.

If legacy systems left unprefixed hashes, migrations must be **strictly scoped to trusted data sources**, validate formats, plan conversions, and never lower general security standards. Very old or insecure formats should prioritize verified password resets.

### 10.4. UpgradeEncoding Alone Does Not Save the System

An encoder may return `false` for `upgradeEncoding` even after organizational security policy has changed, or if version metadata is unclear. Check the implementation and test it. Moreover, `upgradeEncoding(...)` **only emits a signal**; without a step that saves the new hash, accounts retain their old hashes.

## 11. Proper Benchmarking: Never Borrow Latency Numbers from Another Laptop

### 11.1. What Must Be Measured

In an environment as close to production as possible, collect:

- `p50/p95/p99` latency of `matches` and `encode` per algorithm/parameter set.
- Peak heap/RSS and GC behavior with 1, 2, 4, 8, ... concurrent hash requests.
- Throughput (verifications completed per second) and queue wait times.
- CPU utilization, memory bandwidth, page faults, and container memory pressure.
- End-to-end login latency, including DB/`UserDetailsService` and filter/authorization overhead.
- Impact of side workloads: regular APIs, batch jobs, caches, and health checks.
- Behavior past limits: bounded queues, 429/503 per policy, circuit breakers/timeouts, metrics; never crashing the JVM.

Do not run `System.currentTimeMillis()` once and lock in system-wide parameters. JIT warm-up, CPU frequency, thermal throttling, GC, random-salt hashing, concurrent load, and virtualization all cause results to vary. A tiny benchmark only proves the code runs; it does not prove brute-force resistance or attack resilience.

### 11.2. Illustrative Latency Measurement Code (Not Standalone)

~~~java
// Inside a benchmark/test with a valid PasswordEncoder and storedHash.
long start = System.nanoTime();
boolean ok = encoder.matches(rawPassword, storedHash);
long elapsedNs = System.nanoTime() - start;
System.out.println("verified=" + ok);
System.out.println("elapsed-ms=" + (elapsedNs / 1_000_000.0));
~~~

This is an **integration snippet**; `encoder`, `rawPassword`, and `storedHash` must be initialized. The `elapsed-ms` output is **not deterministic**, as it depends on runtime conditions. In real performance testing, use JMH or load tools with warm-up, statistical sampling, and container telemetry to avoid misleading measurements.

### 11.3. Choose Parameters for the Service, Not Just One User

Suppose `matches` takes an acceptable duration for UX at concurrency=1. You still must test concurrency=8/16. If memory pressure triggers stop-the-world GC pauses or OOMs, raising parameters can actually **reduce operational security** by making it easier for attackers to deny legitimate logins.

Choosing a cost factor is a multi-objective optimization problem:
- Slow down offline guessing on leaked hashes.
- Keep valid logins within acceptable latency.
- Maintain headroom under peak traffic and anomaly spikes.
- Retain the ability to update parameters as hardware/algorithms evolve.

Record the **policy version**, dated/hardware-annotated benchmarks, and an upgrade plan, rather than merely writing "Argon2 is secure" without measurements.

## 12. Preventing Denial of Service When Passwords Deliberately Consume Memory

Memory-hard KDFs help resist offline cracking, yet also make **every online login** consume server RAM/CPU. An attacker can flood login requests to create memory pressure if controls are missing.

Measures to combine:

1. **Multi-dimensional rate limiting:** by IP/source, account, session/device/risk; avoid locking out by username alone, which lets attackers DoS other users' accounts.
2. **Bounded concurrency:** use a queue/semaphore or dedicated pool to cap simultaneous hash operations. Avoid unbounded queues during traffic spikes.
3. **Global resource budget:** reserve headroom for the database, regular APIs, and health checks; check container limits.
4. **Reasonable timeouts:** client and server timeouts must align with measured verification times. Limit synchronized retry storms.
5. **Monitoring:** active hash count, queue depth, rejection rate, heap usage, RSS, GC, OOM-kills, and p95 login latency.
6. **Session/token design:** after verifying the password once, issue a session or appropriate short-lived token instead of making clients resend passwords to be re-hashed on every API request.
7. **Isolate identity workloads if needed:** separate login workers, resource isolation, bounded auto-scaling, preventing KDF load from starving core business data/APIs.

**It is not recommended to drastically lower the cost factor just to "cure" login spam.** Design traffic and resource controls first, then choose parameters from sound benchmarks. If forced to lower cost during an incident, perform a security review and recovery plan because offline guessing becomes cheaper.

### 12.1. Concurrency Estimation Example by Headroom

Assume a dedicated hashing budget of 320 MiB and base scrypt at 64 MiB/op:

\[
C_{\text{theoretical}} = \left\lfloor \frac{320}{64} \right\rfloor = 5.
\]

Do not immediately allow 5 concurrent operations: overhead memory, GC, and load spikes also exist. Start with a lower limit based on benchmarks, measure in practice, and scale carefully. With Argon2 m=16 MiB and the same budget, division gives 20; **that does not mean 20 concurrent calls also meet latency/CPU SLAs**, since the bottleneck may shift from RAM to CPU or memory bandwidth.

### 12.2. Do Not Confuse Login Concurrency with Total HTTP Threads

An application with 200 servlet threads is not necessarily verifying 200 passwords at once; many requests only use bearer tokens or sessions. Yet when an attacker targets the login endpoint, concurrent hashes can approach the maximum parallel requests allowed. Therefore, limits must guard the **actual verification path**, not just adjust total HTTP threads.

## 13. Security Issues Often Overlooked

### 13.1. Random Salt Is Not Pepper

**Salt** is generated uniquely per password by the encoder and stored alongside the hash; it need not be secret. **Pepper** is a system-level secret managed separately (KMS/HSM or secret store) that may be added under a vetted design. Never manually inject pepper via ad-hoc string concatenation without versioning/rotation rules assuming every algorithm supports it seamlessly.

If pepper is used, losing it can force password resets, and rotation requires dedicated design; it does not replace salt or a memory-hard KDF.

### 13.2. Leaked Hashes Can Still Be Cracked Offline

Even scrypt/Argon2 with sensible work factors cannot make weak passwords completely safe. Attackers holding hashes and salts can run offline dictionary attacks. You still need strong password policies, MFA/phishing-resistant authentication where warranted, credential-stuffing detection, and an incident response plan if the database leaks.

### 13.3. Never Write Raw Passwords/Hashes to Logs

Never log `rawPassword`, password hashes, encoded storage strings, `Authentication.toString()` containing credentials, or request bodies containing passwords. Even though hashes are one-way outputs, they remain sensitive material useful for offline cracking.

### 13.4. Never Construct Salts from Username or Timestamp

Standard encoders generate cryptographically random salts; never replace them with `salt = username`, user ID, timestamp, or a global constant. Predictable or colliding salts undermine resistance to precomputed tables and identical-password correlation.

### 13.5. Do Not Assume Larger Hash Output Means Stronger Security

`hashLength=32` bytes is the output size; raising it to 64 bytes **does not double password-guessing resistance** when password entropy is low. Work factor, salt, password policy, and server protection matter far more than merely enlarging output length.

### 13.6. Cloud and Serverless Considerations

In small containers or memory-constrained serverless functions, the 64 MiB scrypt preset can strain the app under concurrency. Serverless also introduces cold starts, memory-tiered CPU allocation, and timeouts; tune parameters from benchmarks tailored to that exact environment.

## 14. Functional and Operational Testing

| Test | Input / Condition | Expectation |
| --- | --- | --- |
| Scrypt round-trip | Correct password, scrypt-generated hash | `matches` returns `true` |
| Scrypt wrong password | Different password, same encoded hash | `false` |
| Argon2 round-trip | Correct password, Argon2-generated hash | `true` |
| Argon2 wrong password | Different password, same encoded hash | `false` |
| Random salt | Two `encode` calls with same password | Usually different encoded strings, yet both match |
| Different formats | Scrypt hash passed directly to Argon2 `matches` | Do not assume compatibility; use matching encoder/ID |
| Delegating legacy hash | `{scrypt-v58}...`, ID in map | `matches` succeeds; `upgradeEncoding` can return true |
| ID missing from map | `{unknown}...` string | Fails safely; never auto-succeeds |
| Null/malformed input | Null, malformed encoded hash | Follows contract/exception rules; never returns true |
| Missing Bouncy Castle | Runtime missing dependency | Build/tests catch the error before production |
| Concurrency | 8/16/32 concurrent login hashes | No OOM; bounded behavior/latency metrics captured |
| Misconfigured `memory` | Passing bytes instead of KiB | Config tests catch wrong parameter scale |
| Migration | Old ID and new ID hashes coexist | Both verify accurately; new encodes use current ID |
| Post-login upgrade | Old hash matches then rehashes | New record committed safely without losing roles/object state |
| Brute-force pressure | Abnormal error traffic spike | Rate limits, queues, and alerts engage |
| Session reuse | Logged-in user with valid session | Passwords are not re-hashed on every API request |
| Cached user | Cached `UserDetails` | Passwords still checked on fresh authentication; cache does not replace login |

**Testing in Spring Boot:** write integration tests with real `DaoAuthenticationProvider`, `UserDetailsService`, and `PasswordEncoder`. A test using only `@WithMockUser` verifies authorization, not password hashing. To prove the KDF works, run real `encode`/`matches` or submit login requests through the real filter/provider chain.

## 15. Very Common Mistakes

1. **Thinking scrypt's `memoryCost=8` means "8 MB".** Wrong: that is `r`, while core memory is roughly `128 × N × r`.
2. **Thinking Argon2's `memory=16384` is in bytes.** Wrong: the unit is KiB, equal to 16 MiB.
3. **Multiplying `m×p` to estimate total Argon2 RAM.** `m` is total memory for the operation, not per-lane memory by default.
4. **Raising `t` and multiplying RAM by `t`.** Pass count primarily increases runtime, not peak RAM multiplied by iterations.
5. **Writing `encode(input).equals(storedHash)`.** Fresh salts cause string equality to fail; use `matches`.
6. **Using SHA-256(password) instead of an adaptive password encoder.** Far too fast to resist offline guessing.
7. **Storing a fixed salt or using username as salt.** Cannot replace random salts generated by standard encoders.
8. **Setting N/m too high on low-RAM nodes without concurrency limits.** Easily triggers OOM/DoS under login load.
9. **Disabling legacy hash format decoding during migration.** Can lock out cohorts of existing users.
10. **Seeing `upgradeEncoding=true` and assuming DB updated itself.** You must write the rehash and persistence step.
11. **Equating raw algorithmic memory estimates with measured RSS.** Ignores GC, native memory, stacks, caches, and multiple processes.
12. **Enabling Argon2 while forgetting Bouncy Castle.** Can fail at runtime even when code compiles.
13. **Comparing Argon2 vs. scrypt preset latencies and declaring one universally stronger/weaker.** Parameters and implementations differ.
14. **Not testing failed logins under high load.** The KDF still runs on wrong passwords for valid accounts.
15. **Treating "password hash matched" as sufficient for authorization.** The provider still checks account status; authorization must still verify roles, authorities, tenant, and resources.
16. **Logging hashes to debug salts.** Hashes are sensitive data usable for offline cracking.
17. **Sending passwords on every request instead of using sessions/short-lived tokens.** Creates unnecessary hashing load.
18. **Choosing parameters from a 1-request benchmark on a personal laptop.** Does not represent production pods or concurrency.
19. **Forgetting retry policies when the identity service slows down.** Retries can multiply active hash operations and accelerate resource exhaustion.
20. **Casually enabling plaintext fallback for unknown-ID hashes.** Opens weak login paths and security vulnerabilities.

## 16. Self-Check Questions

**Question 1:** In `new SCryptPasswordEncoder(65536,8,1,32,16)`, does parameter `8` mean 8 MB?  
**Answer:** No, that is `r`. Core memory is roughly `128×65536×8 = 64 MiB`.

**Question 2:** Argon2's constructor takes `memory=16384`. Does one hash take exactly 16,384 bytes?  
**Answer:** No, the memory parameter is measured in KiB. Configured memory is about 16 MiB, before overhead.

**Question 3:** Does increasing Argon2 `iterations` from 2 to 4 raise RAM from 16 to 32 MiB?  
**Answer:** Not in that sense. `t` raises pass count/compute work; `m` remains the algorithm's primary memory budget.

**Question 4:** At peak phase concurrently, what is the minimum large-table memory across 8 requests using the 64 MiB scrypt preset?  
**Answer:** Estimated **512 MiB** before JVM/implementation overhead. Measure in practice to set limits.

**Question 5:** Is `encode("abc").equals(storedHash)` valid for checking logins?  
**Answer:** No. Random salts make hashes differ; use `matches("abc", storedHash)`.

**Question 6:** If `matches` returns true, can you skip checking enabled/locked status?  
**Answer:** No. `PasswordEncoder` only checks the password; `DaoAuthenticationProvider` also checks account status, and authorization checks permissions.

**Question 7:** Why must Bouncy Castle be on the classpath when using `Argon2PasswordEncoder`?  
**Answer:** Spring Security's implementation uses Bouncy Castle for Argon2; missing the dependency causes runtime errors.

**Question 8:** Does `PasswordEncoderFactories.createDelegatingPasswordEncoder()` create new hashes with Argon2 by default?  
**Answer:** No. In Spring Security 6.5, the default factory encodes under ID `bcrypt`; other algorithms are mapped for compatibility/verifying matching hashes.

**Question 9:** Can all stored bcrypt hashes be converted to Argon2 without knowing raw passwords?  
**Answer:** You cannot convert a one-way hash into an equivalent Argon2 hash of the original password without the password; use rehash-on-successful-login or a verified reset flow.

**Question 10:** Why is `upgradeEncoding` useful?  
**Answer:** It signals that the current hash may need upgrading to the new encoding policy. However, DB update code (or `UserDetailsPasswordService`) is required; it does not write by itself.

**Question 11:** Does `p=4` in Argon2 mean RAM = `4×m`?  
**Answer:** No. `m` is total configured memory; lane count changes how it is partitioned, not a simple multiplication.

**Question 12:** If a benchmark shows 300 ms per hash, is it safe to run 1,000 concurrently?  
**Answer:** No. You must check RAM, CPU, thread queues, container limits, p95/p99 latency, and rate-limiting policies.

**Question 13:** When should scrypt be replaced with Argon2?  
**Answer:** When your organization selects the appropriate algorithm, supported libraries/versions are available, benchmarks fit resource budgets, and a migration path preserves verification of old hashes. Never pick solely based on a preset's MiB number.

**Question 14:** Why does a memory-hard KDF not replace rate limiting?  
**Answer:** It makes offline guessing expensive, yet also consumes server memory per login. Online attackers can still send floods of requests to exhaust resources without rate limits.

## 17. Production Adoption Checklist

- [ ] Use an adaptive `PasswordEncoder` with random salts and never store plaintext passwords.
- [ ] Explicitly define scrypt `N,r,p` or Argon2id `m(KiB),t,p` along with hash format/version.
- [ ] Verify byte/KiB/MiB units, documenting formulas and assumptions in operational runbooks.
- [ ] Benchmark `matches` and `encode` on production-like hardware/containers with warm-up and statistical sampling.
- [ ] Measure peak heap/RSS/GC, throughput, and p95 login latency under concurrency, not single-request latency.
- [ ] Reserve JVM headroom and bound the number of concurrently executing hashes.
- [ ] Implement rate limiting and safe degradation responses when the identity hashing pool is saturated.
- [ ] If using Spring Security Argon2, audit Bouncy Castle version and dependencies.
- [ ] If using `DelegatingPasswordEncoder`, confirm legacy ID formats/hashes remain mapped properly.
- [ ] Never enable plaintext fallback for unknown-format hashes.
- [ ] Plan cost-factor increases over time with rehashing on successful login.
- [ ] Test `UserDetailsPasswordService`/DB updates for atomicity and ensure no credentials leak.
- [ ] Never print raw passwords, password hashes, salts, or tokens into application logs.
- [ ] Enforce HTTPS, protect the database, and restrict read access to hashes and backups.
- [ ] Enforce account status, MFA where needed, and authorization independently of `matches`.
- [ ] Monitor hash success/failure rates, queue depth, timeouts, GC, memory pressure, OOMs, and p95/p99 login latency.
- [ ] Establish a procedure for changing cost under growing load: canary, benchmark, rollback, and rehash/hash-version policies.

**Remember:** Scrypt and Argon2 increase offline password-guessing cost by requiring **CPU and memory**. Yet that same cost is **paid by your login service on every verification**. Therefore, tune parameters on both axes: strong enough against attacks while bounding concurrency and keeping operational headroom. Spring Security handles `encode/matches` and versioned hash formats; the application itself must design the database, migrations, rate limiting, and memory budget.

### Official Documentation and Standards

- Spring Security 6.5 — Password Storage: https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html
- Spring Security 6.5 — SCryptPasswordEncoder Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/scrypt/SCryptPasswordEncoder.html
- Spring Security 6.5 — Argon2PasswordEncoder Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/argon2/Argon2PasswordEncoder.html
- Spring Security 6.5 — DelegatingPasswordEncoder Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html
- Spring Security 6.5 — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- RFC 7914 — scrypt Password-Based Key Derivation Function: https://www.rfc-editor.org/rfc/rfc7914
- RFC 9106 — Argon2 Memory-Hard Function for Password Hashing and Proof-of-Work Applications: https://www.rfc-editor.org/rfc/rfc9106
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
