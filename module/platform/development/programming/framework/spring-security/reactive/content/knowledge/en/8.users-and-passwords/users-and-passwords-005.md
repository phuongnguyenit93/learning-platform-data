# Password Hashing with BCrypt, Argon2, and Choosing Computational Cost

## Lesson Objectives

In a Spring Security Reactive application, username/password authentication is more than comparing two strings. The system must **verify passwords against one-way hashes** using a salted algorithm with an intentionally chosen computational cost. BCrypt and Argon2id both aim to make bulk password guessing expensive; however, they have different cost models and deployment characteristics.

After this lesson, you can:

1. Distinguish password hashing from decryptable encryption, general-purpose data hashing, and plaintext password storage.
2. Explain salt, work factor, cost, and why the same password can produce different hashes.
3. Use Spring Security's `BCryptPasswordEncoder` and `Argon2PasswordEncoder` to call `encode`/`matches` properly.
4. Explain BCrypt's cost and Argon2id's three parameters (`memory`/`iterations`/`parallelism`), and understand bcrypt's 72-byte limit.
5. Use `DelegatingPasswordEncoder` to accept both old and new hashes with `{id}` prefixes, and design hash upgrades upon successful user login.
6. Choose parameters by benchmarking on real infrastructure, accounting for login latency, concurrent resources, brute-force resistance, and denial-of-service risk.
7. Build a Java 17+ Spring WebFlux application with sample accounts using **two algorithms**, verifying authentication via HTTP and automated tests.

This lesson belongs to the **Users and Passwords** topic of **Spring Security – Reactive**. The Java portion uses Spring Boot 3.x, Spring Security 6.x, Java 17+, and Gradle. The cost values in the examples are **practice configurations that must be re-benchmarked**, not fixed recommendations for every system.

## 1. Why Must Passwords Never Be Stored in Plaintext?

Users submit passwords during registration or login. The system needs to know whether the credential they enter matches the credential set previously, but in principle **never needs the ability to recover the original password**.

Wrong storage approach:

```text
username | password
alice    | MyStrongPass!2026
bob      | AnotherPassword!
```

If a database, backup, log file, or export leaks, every plaintext password is exposed immediately; users may also reuse those passwords on other services.

Principled storage approach:

```text
username | password_hash
alice    | {bcrypt}$2a$12$<salt-and-hash-bytes>
bob      | {argon2@SpringSecurity_v5_8}$argon2id$v=19$m=16384,t=2,p=1$...
```

The strings above only **illustrate format** and are not valid hashes for authentication. `<...>` denotes placeholders, not real data. `{bcrypt}` or `{argon2@SpringSecurity_v5_8}` is **Spring Security's encoder routing prefix**, while `$2a$...` or `$argon2id$...` is the algorithm's format. Real hash values are produced by `PasswordEncoder.encode(...)` with random salts.

### 1.1. One-Way Hashing Is Not Encryption

- **Encryption** uses keys and is designed for decryption; it fits data that must be recovered verbatim.
- **Password hashing** uses an intentionally slow password-verification algorithm that stores salt and check parameters; there is no "decrypt" function that returns the password.
- **Fast digests** such as SHA-256, MD5, or SHA-1 applied once are not a secure password storage design. They are engineered to compute quickly, enabling attackers to test huge numbers of passwords per second after stealing a database.
- **Salt** is not a secret password. Salt should be generated randomly per hash and is typically stored right inside the hash string. Two users with the same raw password still receive two different hashes, reducing the effectiveness of precomputed hash tables and preventing detection of two users sharing a password.
- **Pepper** is an optional system-level secret used in some threat models; it **does not replace salt**, must be managed via a secret store/HSM/KMS, and needs a key-rotation strategy. Never hardcode a pepper in source code or logs.

### 1.2. Registration and Login Flow

```text
Registration:
  raw password
    -> PasswordEncoder.encode(raw)
    -> hash containing algorithm, parameters, salt, digest
    -> save hash to database

Login:
  username + raw password just entered by user
    -> look up stored hash by username
    -> PasswordEncoder.matches(raw, storedHash)
    -> true / false
    -> Spring Security decides Authentication
    -> application uses authenticated Authentication for authorization
```

**Do not** run `encoder.encode(raw).equals(storedHash)`. Because each `encode` call typically generates a random salt, the new hash can differ from the old hash even when the raw password is identical. `matches` reads the metadata embedded in the old hash, performs the check using the matching algorithm, and returns a boolean.

## 2. BCrypt: Exponential Work Factor

BCrypt is a long-standing, widely deployed password hashing scheme. Spring Security provides `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder`.

Example:

```java
PasswordEncoder bcrypt = new BCryptPasswordEncoder(12);

String hash1 = bcrypt.encode("sample-password");
String hash2 = bcrypt.encode("sample-password");

boolean correct = bcrypt.matches("sample-password", hash1);
boolean wrong = bcrypt.matches("different-password", hash1);
boolean sameHash = hash1.equals(hash2);
```

This snippet uses imports `PasswordEncoder` and `BCryptPasswordEncoder`. Expected result:

```text
correct == true
wrong == false
sameHash == false   (with independent random salts)
```

Each BCrypt hash typically looks like `$2a$12$...`, `$2b$...`, or an implementation-specific variant. Two digits like `12` carry the cost factor; the hash also contains the salt and digest data. Do not strip out what follows `$` and store it across separate columns unless there is a verified compatibility requirement.

### 2.1. The `strength` Cost

`new BCryptPasswordEncoder(strength)` takes BCrypt's work factor. With `strength = 12`, core work scales roughly on the order of `2^12` rounds. Increasing cost by 1 unit roughly doubles hashing work; going from 10 to 12 typically takes roughly four times as long, **without** guaranteeing absolute timings across all CPUs.

Relative comparison example:

| BCrypt strength | Relative core cost vs. 10 | Meaning |
|---:|---:|---|
| 10 | 1× | Illustrative baseline |
| 11 | 2× | Roughly double the work |
| 12 | 4× | Roughly four times |
| 13 | 8× | Roughly eight times |
| 14 | 16× | Can cause pressure under concurrent logins |

These ratios represent **work-model relationships**, not SLA guarantees. Processor model, JVM warmup, library version, CPU speed, container throttling, and concurrent load all affect real latency.

Too low a strength lets attackers guess passwords faster. Too high a strength forces **your own server** to do heavy work on every login, potentially creating a bottleneck/DoS. Decisions require benchmarking and login rate controls, not maximizing the strength number.

### 2.2. BCrypt's 72-Byte Input Limit

Traditional BCrypt processes passwords up to roughly **72 bytes**, not 72 Java characters or 72 Unicode characters. A Vietnamese character or emoji can occupy multiple bytes in UTF-8. Implementations may truncate bytes beyond the limit or enforce specific checks; never assume every password length is fully verified.

For example, if policy allows long passphrases, verify the **encoded byte length limit**, the exact behavior of the active encoder, and compatibility rules. Never tack on a custom SHA-256 pre-hash before feeding the digest into BCrypt without a reviewed security design, verification, and migration rules: ad-hoc pre-hashing can introduce encoding, null-byte, and semantics pitfalls.

For new systems needing flexible long passwords and able to provision adequate memory, Argon2id is a strong candidate.

### 2.3. Random Salt and Verification

The BCrypt salt is normally stored inside the hash itself, requiring no separate `salt` column for `matches` to work. For the same password:

```java
String a = bcrypt.encode("secret");
String b = bcrypt.encode("secret");

assert bcrypt.matches("secret", a);
assert bcrypt.matches("secret", b);
assert !a.equals(b);
```

`assert` here illustrates the concept; in automated tests use explicit JUnit assertions rather than relying on Java `assert`, which can be disabled when running without `-ea`.

## 3. Argon2id: Combining Time and Memory Costs

Argon2 is a modern password hashing family. **Argon2id** combines Argon2i's side-channel resistance with Argon2d's resistance to low-memory parallel attacks; it is commonly chosen for password hashing. Spring Security provides `org.springframework.security.crypto.argon2.Argon2PasswordEncoder` using the Argon2id variant in 6.x releases.

Encoder example using Spring Security's provided profile:

```java
PasswordEncoder argon2 =
    Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();

String hash = argon2.encode("sample-password");

boolean ok = argon2.matches("sample-password", hash);
boolean bad = argon2.matches("wrong", hash);
```

Result:

```text
ok == true
bad == false
```

Argon2id hashes normally use the PHC string format:

```text
$argon2id$v=19$m=16384,t=2,p=1$<salt-base64>$<hash-base64>
```

This is a **format illustration**, not a real hash. `m` is memory cost (in KiB), `t` is the number of iterations/passes, and `p` is parallelism (lanes). Values can differ based on the constructor, version, or configuration you choose; inspect hashes generated by your actual application.

### 3.1. Three Parameters and Trade-Offs

| Parameter | Meaning | Trade-Off |
|---|---|---|
| `memory`/`m` | Memory allocated per hashing call, usually in KiB | Increasing memory cost increases RAM per attempt; with many concurrent requests, total RAM can spike sharply |
| `iterations`/`t` | Number of passes over memory | Increases CPU time and usually RAM retention duration |
| `parallelism`/`p` | Number of lanes / ability to split work in parallel | Can alter latency and CPU distribution depending on implementation; does not automatically mean exactly `p` Java threads |
| `saltLength` | Random salt bytes per hash | Should be sufficiently large, allocated by the encoder |
| `hashLength` | Output hash length | Typically kept at standard/default values |

Unlike BCrypt which relies mainly on CPU, Argon2id is designed to be **memory-hard**, meaning guessing passwords with significantly less memory incurs extra cost. This raises attack costs on GPUs/ASICs, but also requires provisioning sufficient RAM and controlling concurrency on your authentication system.

### 3.2. Explicit Parameter Constructor

In Spring Security 6.x, the common constructor has this parameter order:

```java
Argon2PasswordEncoder tuned = new Argon2PasswordEncoder(
    16,       // saltLength: byte
    32,       // hashLength: byte
    1,        // parallelism
    65536,    // memory: KiB = 64 MiB
    3         // iterations
);
```

This is an **experimental configuration**, not a mandatory default and not yet a production-benchmarked parameter set. With `m=65536` KiB, each computation requires roughly 64 MiB of memory in addition to JVM/implementation overhead. If 50 requests hash concurrently, **50 × 64 MiB alone is roughly 3.2 GiB**, excluding other heap/native memory and implementation details. "Stronger" settings can exhaust memory or render the server unresponsive to legitimate logins.

A good starting point to learn the API is:

```java
Argon2PasswordEncoder defaults =
    Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();
```

The method name includes `v5_8` to tie it to the default set defined as of Spring Security 5.8. Do not interpret `v5_8` as an Argon2 version or encryption key; it is the library's default profile name. Check `m,t,p` in actual generated hashes to know which parameters are used rather than assuming the method name means "newest optimal".

### 3.3. Bouncy Castle Dependency

Spring Security uses Bouncy Castle for `Argon2PasswordEncoder` in the 6.x line. If a project lacks the matching provider, encode/matches calls can fail with missing class or initialization errors.

With Gradle, add a compatible Bouncy Castle version approved against your project's BOM/dependency policy. Example to run this demo:

```groovy
implementation 'org.bouncycastle:bcprov-jdk18on:1.78.1'
```

This is a **specific example version**, not a claim of being the latest Bouncy Castle release. When upgrading Spring Security/JDK, check release notes, CVEs, and your project's dependency resolution, and update to a tested dependency. Never swap in unverified provider classes or homegrown crypto.

## 4. BCrypt vs. Argon2id: Comparison by Threat Model

| Criterion | BCrypt | Argon2id |
|---|---|---|
| Prevalence in legacy systems | Very widespread, many existing hashes | Fits new systems and controlled migrations |
| Input | Traditional 72-byte limit to watch | Supports flexible long passphrases per implementation |
| Primary cost | CPU, controlled by logarithmic strength | CPU + RAM, controlled by m/t/p |
| Resistance to parallel password guessing | Yes; tuned via work factor | Memory-hard, adding a RAM control dimension |
| Resources to size in production | CPU latency/concurrency | CPU + RAM + concurrency |
| Running on RAM-constrained infrastructure | Usually more predictable RAM footprint | Must budget memory allocations and concurrent request bursts |
| Legacy hash compatibility | Can keep verifying directly | Can use `DelegatingPasswordEncoder` to accept legacy hashes during algorithm migration |

There is no universal answer like "every system must use Argon2id at level X" or "BCrypt 10 is safe forever". The choice depends on user password characteristics, actual CPU/RAM, authentication resource budgets, credential-stuffing defenses, and compliance requirements. Argon2id is generally preferable for new systems when operations and libraries allow; BCrypt remains sensible for maintaining existing hashes and gradually raising cost based on benchmark results.

### 4.1. A Decision Scenario

Suppose an auth cluster sees high concurrent logins with low per-container RAM limits. Running Argon2id at 64 MiB/verification on a public endpoint could trigger out-of-memory errors under heavy load, even before counting heap and other requests. An Argon2id configuration with lower `m` and sufficient `t`, or BCrypt with an appropriate cost, **combined with rate limiting, concurrency quotas, and proper resource architecture**, can protect system availability better.

Conversely, when ample RAM is available, concurrent attempts are bounded, and strong resistance against offline password cracking is desired, a memory-hard Argon2id setup is advantageous. Never skip logging/monitoring and backpressure just because you chose a strong algorithm.

## 5. Spring Security's PasswordEncoder API

Core interface:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

This is an **abbreviated signature for learning**, not an interface to define yourself. The `upgradeEncoding` method lets an encoder indicate that an existing hash should be re-encoded under the new configuration (when supported by the implementation). Returning `true` does not automatically update the database.

To verify a password, **do not** use:

```java
String encoded = encoder.encode(rawPassword);
return encoded.equals(storedHash);  // Wrong: different salt
```

Correct:

```java
return encoder.matches(rawPassword, storedHash);
```

Code paths must avoid logging `rawPassword`, putting hashes in HTTP responses, or storing hashes in URLs. The encoder needs the exact stored value. Never trim, lowercase, or normalize passwords inconsistently after registration: changing a single character changes the hash result.

## 6. Supporting Multiple Formats with DelegatingPasswordEncoder

When migrating from BCrypt to Argon2id, you cannot "convert" an existing BCrypt hash into Argon2id **without knowing the raw password**. Because hashing is one-way, you must retain the ability to verify BCrypt until users log in again or change their passwords. Spring Security provides `DelegatingPasswordEncoder`, allowing each hash string to carry an `{id}` prefix:

```text
{bcrypt}$2a$12$...
{argon2@SpringSecurity_v5_8}$argon2id$v=19$m=16384,t=2,p=1$...
```

These are illustrative formats; every real hash contains a valid salt and digest payload.

### 6.1. Mapping id → encoder

```java
Map<String, PasswordEncoder> encoders = new HashMap<>();

encoders.put(
    "bcrypt",
    new BCryptPasswordEncoder(12)
);

encoders.put(
    "argon2@SpringSecurity_v5_8",
    Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8()
);

PasswordEncoder delegating = new DelegatingPasswordEncoder(
    "argon2@SpringSecurity_v5_8",
    encoders
);
```

This snippet requires imports `java.util.Map`, `HashMap`, Spring's `PasswordEncoder`, `DelegatingPasswordEncoder`, `BCryptPasswordEncoder`, and `Argon2PasswordEncoder`; the full runnable class is in Section 7.

- `idForEncode` is `"argon2@SpringSecurity_v5_8"`: when calling `delegating.encode(raw)`, new hashes are saved with that id's prefix.
- When calling `delegating.matches(raw, "{bcrypt}...")`, the delegate selects BCrypt to verify the legacy hash.
- When calling `delegating.matches(raw, "{argon2@SpringSecurity_v5_8}...")`, the delegate selects the matching Argon2 encoder profile.
- If an unsupported id is encountered, never fall back to `NoOpPasswordEncoder` or treat the password as valid by default. Your migration design must explicitly detect and handle legacy hashes missing ids or having unknown formats.

**Watch the id names:** `{argon2}` and `{argon2@SpringSecurity_v5_8}` are two distinct ids in the delegation map. Both represent Argon2id, yet they may correspond to different Spring Security parameter profiles. If a database contains both forms, map both to their respective encoders and test thoroughly. Never rewrite prefix strings on old hashes via text manipulation without proper verification/migration.

### 6.2. Why Not Use NoOpPasswordEncoder?

`NoOpPasswordEncoder` is only compatible with plaintext in controlled migration scenarios; it is unsuitable for storing production credentials. Falling back `defaultPasswordEncoderForMatches` to NoOp to "fix missing id errors" can cause dangerous strings to be interpreted as raw passwords. If you have bare `$2a$...` legacy hashes without `{bcrypt}`, write a tested migration and tag the proper format after verification rather than assuming unrecognized data is valid.

## 7. Runnable Spring WebFlux Demo: Two Accounts, Two Algorithms

We will build a WebFlux application with:

- `GET /me`: requires HTTP Basic authentication and returns the authenticated username.
- User `legacy`: BCrypt hash with cost 12, stored with the `{bcrypt}` prefix.
- User `modern`: Argon2id hash using the `v5_8` profile, stored with the `{argon2@SpringSecurity_v5_8}` prefix.
- `DelegatingPasswordEncoder`: verifies both formats within the same application.
- `WebTestClient`: tests valid, invalid, and missing-credential authentication cases.

**This is a learning demo:** sample credentials intentionally live in source code and an in-memory user store; do not use them in production, and do not expose endpoints that register or return hashes.

### 7.1. Creating the Project and Dependencies

Create the project with [Spring Initializr](https://start.spring.io/) using Gradle, Java 17+, Spring Boot 3.x, and dependencies:

- Spring Reactive Web: `spring-boot-starter-webflux`
- Spring Security: `spring-boot-starter-security`
- Spring Boot Starter Test: `spring-boot-starter-test`
- Spring Security Test: `spring-security-test`

Add Bouncy Castle. The `dependencies` block in the Initializr-generated `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.bouncycastle:bcprov-jdk18on:1.78.1'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

This is only the **`dependencies` block**, not the entire Gradle file. Keep the Spring Boot plugin, repositories, dependency management, and Java toolchain generated by Initializr. Do not add `spring-boot-starter-web`: when both MVC and WebFlux starters are present, Spring Boot 3.x typically defaults to inbound Servlet/MVC, changing the security pipeline.

Layout:

```text
src/main/java/demo/passwordcost/
  PasswordCostApplication.java
  PasswordSecurityConfig.java
  MeController.java
src/test/java/demo/passwordcost/
  PasswordIntegrationTests.java
  EncoderBehaviorTests.java
```

### 7.2. `PasswordCostApplication.java`

```java
package demo.passwordcost;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordCostApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasswordCostApplication.class, args);
    }
}
```

### 7.3. `PasswordSecurityConfig.java`

```java
package demo.passwordcost;

import java.util.HashMap;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class PasswordSecurityConfig {

    @Bean
    public PasswordEncoder passwordEncoder() {
        Map<String, PasswordEncoder> encoders = new HashMap<>();
        encoders.put("bcrypt", new BCryptPasswordEncoder(12));
        encoders.put(
            "argon2@SpringSecurity_v5_8",
            Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8()
        );
        return new DelegatingPasswordEncoder(
            "argon2@SpringSecurity_v5_8",
            encoders
        );
    }

    @Bean
    public MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Source code is for practice only; do not keep plaintext in production.
        UserDetails legacy = User.withUsername("legacy")
            .password("{bcrypt}" +
                new BCryptPasswordEncoder(12).encode("legacy-pass"))
            .roles("USER")
            .build();

        UserDetails modern = User.withUsername("modern")
            .password(encoder.encode("modern-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(legacy, modern);
    }

    @Bean
    public ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {
        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {
        return http
            .authenticationManager(manager)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Configuration explanation:**

1. `PasswordEncoder` is a `DelegatingPasswordEncoder`. **New** hashes use Argon2id, while prefixed BCrypt hashes are still verified.
2. The two `UserDetails` do not store plaintext in their password property; the encoders generate hashes at startup. Fresh salts are generated each time the app starts, so do not compare exact hash strings across runs.
3. `MapReactiveUserDetailsService` fits demos and tests; production uses an account repository and appropriate lifecycle.
4. `UserDetailsRepositoryReactiveAuthenticationManager` is constructed explicitly with `ReactiveUserDetailsService` and configured via `setPasswordEncoder(encoder)`; this clarifies which encoder participates in matching both hash formats.
5. `ServerHttpSecurity.authenticationManager(manager)` wires the configured manager into the WebFlux security chain.
6. `authorizeExchange` requires authentication for `/me` and denies other routes in the demo, enables `httpBasic` for curl testing, and disables form login so the API does not redirect to an HTML page.
7. Password hashing is a **credential verification mechanism**, not a permission-assignment mechanism. `.roles("USER")` grants authority `ROLE_USER`; this lesson only requires `authenticated()`. In real applications, design separate authorization for user data.

### 7.4. `MeController.java`

```java
package demo.passwordcost;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping("/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> "hello " + name);
    }
}
```

`ReactiveSecurityContextHolder` reads the context from the HTTP request's Reactor subscription after Spring Security authenticates it. Do not use the default thread-local `SecurityContextHolder.getContext()` to guess the principal in WebFlux.

### 7.5. Running and Verifying with HTTP

From the Gradle project root directory:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

Once the server is listening on `localhost:8080`, in another terminal:

```bash
curl -i http://localhost:8080/me
curl -i -u legacy:legacy-pass http://localhost:8080/me
curl -i -u modern:modern-pass http://localhost:8080/me
curl -i -u legacy:wrong-pass http://localhost:8080/me
```

In Windows PowerShell, you can use `curl.exe` to avoid the `curl` alias. Expected:

| Request | HTTP status | Body on success |
|---|---:|---|
| `GET /me` without credentials | `401` | No fixed body required |
| `GET /me` with legacy | `200` | `hello legacy` |
| `GET /me` with modern | `200` | `hello modern` |
| `GET /me` with wrong password | `401` | No fixed body required |

The `WWW-Authenticate` header, error body, and logs may differ across versions/configurations. HTTP Basic only Base64-encodes credentials, **without encrypting transport**; use only over HTTPS in production. Having both legacy and modern log in successfully proves `DelegatingPasswordEncoder` accepts both formats, not that they have identical cost.

## 8. Testing Encoder Behavior and the HTTP Chain

### 8.1. Integration Tests with WebTestClient

Create `src/test/java/demo/passwordcost/PasswordIntegrationTests.java`:

```java
package demo.passwordcost;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class PasswordIntegrationTests {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousCannotAccessProfile() {
        client.get().uri("/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void bcryptLegacyHashCanAuthenticate() {
        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("legacy", "legacy-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello legacy");
    }

    @Test
    void argon2ModernHashCanAuthenticate() {
        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("modern", "modern-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello modern");
    }

    @Test
    void incorrectPasswordIsRejected() {
        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("legacy", "wrong-pass"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

These are HTTP tests against a server started on a random port. They verify both request authentication and the WebFlux security chain, rather than only calling `matches` in a unit test. Never hardcode hashing durations in assertions; CI machines have different performance than local machines.

### 8.2. Encoder Unit Tests, Salt, and the Upgrade Flag

Create `src/test/java/demo/passwordcost/EncoderBehaviorTests.java`:

```java
package demo.passwordcost;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class EncoderBehaviorTests {

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    MapReactiveUserDetailsService users;

    @Test
    void newHashesUseArgon2AndRandomSalt() {
        String first = encoder.encode("a-demo-password");
        String second = encoder.encode("a-demo-password");

        assertTrue(first.startsWith(
            "{argon2@SpringSecurity_v5_8}$argon2id$"));
        assertTrue(second.startsWith(
            "{argon2@SpringSecurity_v5_8}$argon2id$"));
        assertNotEquals(first, second);
        assertTrue(encoder.matches("a-demo-password", first));
        assertFalse(encoder.matches("wrong", first));
    }

    @Test
    void legacyBcryptRemainsVerifiableAndCanBeFlaggedForUpgrade() {
        String oldHash = users.findByUsername("legacy")
            .block().getPassword();

        assertTrue(oldHash.startsWith("{bcrypt}"));
        assertTrue(encoder.matches("legacy-pass", oldHash));
        assertTrue(encoder.upgradeEncoding(oldHash));
    }

    @Test
    void wrongPasswordMustNeverMatch() {
        String modernHash = users.findByUsername("modern")
            .block().getPassword();

        assertTrue(encoder.matches("modern-pass", modernHash));
        assertFalse(encoder.matches("legacy-pass", modernHash));
    }
}
```

`.block()` appears **only in JUnit tests** to read `UserDetails` from the reactive user store, never in a WebFlux handler/event loop. This test does not require checking exact hash strings due to random salting. The delegate's `upgradeEncoding` is expected to return `true` for the BCrypt hash when the new id is Argon2; it is **only a signal that an upgrade is needed**, and does not write to the database itself.

Run:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

With the Spring Boot 3.x/Java 17+ project and dependencies in Section 7, **7 tests are expected to pass**: 4 integration tests and 3 encoder tests. This is an expected result, not a claim the tests were executed; check actual Gradle/JUnit logs to confirm. If failures occur, check the Bouncy Castle dependency, file package names, security beans, Spring Boot version configuration, and test port access.

## 9. Designing Hash Upgrades on Successful Login

An application may hold records spanning many years. Switching algorithms immediately should not force you to store plaintext or reset passwords for all users unnecessarily.

The safe strategy is **rehash on successful login**:

```text
1. User sends username + raw password over a protected connection.
2. Repository reads the current hash, e.g., {bcrypt}$2a$10$...
3. DelegatingPasswordEncoder.matches(raw, storedHash):
     - picks encoder by {id}
     - verifies password
4. If wrong: reject authentication, do not rehash and do not store plaintext.
5. If right: allow authentication to proceed.
6. If encoder.upgradeEncoding(storedHash) == true:
     - encode(raw) using active profile, generating a new salt
     - write new hash using a conditional operation
     - do not log raw password/hash
7. Subsequent logins verify using the new format.
```

At step 6, prevent overwrites when two requests update the hash concurrently. Example **compare-and-swap** mechanism:

```sql
UPDATE users
SET password_hash = :new_hash
WHERE username = :username
  AND password_hash = :old_hash;
```

This is an **illustrative SQL statement** for a corresponding repository, not a standalone R2DBC query. Check the updated row count (0 or 1). If 0, the hash may have changed concurrently or the password was just reset; **do not** overwrite the newer value with a hash of the old credential. Race-handling policy depends on business logic and re-authentication as needed.

### 9.1. Reactive Service Pseudocode with Blocking Boundaries

`PasswordEncoder.encode` and `matches` are CPU/memory-heavy and typically synchronous. A custom reactive service can isolate them on a controlled scheduler:

```java
// Logic fragment inside a service with encoder and reactive repository injected.
// UserRecord/VerifyResult/repository are application-defined domain APIs.
public Mono<Boolean> verifyAndUpgrade(
        String username, String submittedPassword) {

    return repository.findByUsername(username)
        .flatMap(user -> Mono.fromCallable(() -> {
            String oldHash = user.passwordHash();
            boolean matched =
                encoder.matches(submittedPassword, oldHash);

            if (!matched) {
                return new VerifyResult(false, null);
            }

            String newHash = encoder.upgradeEncoding(oldHash)
                ? encoder.encode(submittedPassword)
                : null;

            return new VerifyResult(true, newHash);
        })
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(result -> {
            if (!result.matched()) {
                return Mono.just(false);
            }

            if (result.newHash() == null) {
                return Mono.just(true);
            }

            return repository.replaceHashIfCurrent(
                    username, user.passwordHash(), result.newHash())
                .thenReturn(true);
        }))
        .defaultIfEmpty(false);
}
```

This is a **design fragment**, not a standalone runnable class because `UserRecord`, `VerifyResult`, and `repository` are project-defined. For `VerifyResult`, you can define `record VerifyResult(boolean matched, String newHash) {}` in Java 17. You must inspect the update count, handle races/transactions, and match the application's real authentication policy; never copy this code into production login without testing.

`boundedElastic` keeps blocking work off the event loop, **but does not make hashing non-blocking** and **does not sufficiently cap concurrent memory-consuming requests on its own**. Password verification can be very heavy; if Argon2id memory is high, cap concurrent hashes (bulkhead/semaphore/queue) and measure actual RAM. A scheduler only switches execution threads rather than creating infinite capacity.

### 9.2. Cases Requiring Dedicated Design

- **Forgot password:** use random, single-use, expiring reset tokens; after verifying the token, hash the new password. Never send back the old password because there is no decryption mechanism.
- **Change password:** require an active session/appropriate authentication, verify the old password when required by policy, then create a new hash with the active profile.
- **Infrequent login accounts:** rehash on login does not help users who never return; a migration path or password reset flow may be needed for long-inactive accounts.
- **Wrong password:** do not upgrade, do not "fix" the hash, and do not disclose whether the user exists in the response.
- **Changing id/encoder profile:** keep verifying old formats until migration completes; test every id present in the database.
- **Hashes without prefixes:** have a strategy to determine the algorithm from trusted metadata and migrate safely; never add an "accept anything" fallback.
- **Raising cost within the same algorithm:** some encoders support `upgradeEncoding` by comparing parameters stored in the hash against the active profile; check exact library-version behavior and test with real hashes.

## 10. Choosing the Work Factor by Measurement, Not Guesswork

The ideal cost makes each password guess expensive enough to raise attack costs while still meeting user experience and legitimate login capacity requirements.

### 10.1. Identifying Targets and Resources

Gather these factors:

- **Latency budget** dedicated to hashing/matching: e.g., a fraction of the p95 login SLA, not just Java handler time.
- **Actual CPU**: model, vCPU count, pod/container CPU limits, frequency throttling.
- **Actual RAM**: pod memory limit, heap/native memory, co-located components.
- **Concurrent authentications** at p95/p99 legitimate traffic and bursts from retries/credential stuffing.
- **Autoscaling instance count** and infrastructure cost under load growth.
- **Queue wait time** when limiting parallel verifications.
- **Login surface protection**: rate limiting by account/IP/device, detection, MFA, controlled CAPTCHA when needed, and cautious login lockout policies to avoid DoS abuse.
- **Cost review cycle**: e.g., periodic reviews or upon hardware upgrades/new advisories, rather than leaving parameters static forever.

Do not optimize solely around `encode` time on a laptop; **login primarily runs `matches` on hashes carrying their stored cost**, and may need to verify multiple legacy profiles. Benchmark both `encode` and `matches` across every active hash type.

### 10.2. Meaningful Benchmarking Methodology

1. Pick several candidate configurations (e.g., BCrypt strength 10/12/13, Argon2id memory 16/32/64 MiB with appropriate iterations).
2. Run on the **same CPU/RAM class and memory limits** as production or a representative staging environment.
3. Use synthetic test data rather than real passwords; allow proper JVM startup/warmup.
4. Measure median/p95/p99 latency for `encode` and `matches`; also report throughput.
5. Test multiple concurrent verification levels, such as 1, 5, 20, 50 (chosen per real traffic, not treated as universal targets).
6. Monitor CPU, RSS/heap, garbage collection, out-of-memory events, queue wait times, and overall response times.
7. Test wrong passwords, nonexistent users, reconnects/timeouts, and traffic bursts; never return responses that make username enumeration easy.
8. Select a configuration meeting both security and SLA goals with headroom for growth/node failures, and roll out via canary when raising cost significantly.
9. Record hardware, JVM, dependency versions, cost settings, and results for future comparisons; ensure benchmarks never log real passwords.

Quick checks with `System.nanoTime()` can help understand mechanics, but do not replace reliable benchmarks (such as JMH) because JIT, warmup, GC, CPU scheduling, and concurrency skew results. Never extrapolate production p95 from a single-threaded loop.

### 10.3. A Mandatory RAM Capacity Calculation

Consider Argon2id with `m = 65536 KiB = 64 MiB`. If you allow 24 verifications to run concurrently, parameter-level memory alone is **approximately**:

```text
24 × 64 MiB = 1536 MiB = 1.5 GiB
```

That is only the parameter allocation model, not exact RSS; there is also JVM, OS, native library, and other request overhead. If a pod has a 1 GiB limit, this clearly signals you must lower concurrency, lower `m`, adjust replica counts, or redesign the authentication path. Never size concurrency off the Netty event-loop thread count and assume hashing is bounded.

### 10.4. Choosing an Initial Configuration Safely

A practical roadmap:

- If a legacy database uses BCrypt: keep verifying with the matching profile encoder, measure current strength, and enable `upgradeEncoding`/rehash on successful login if needed; never break existing users' logins.
- If building greenfield with available memory: consider Argon2id, start from the library's standard profile as a baseline, measure, and tune `m,t,p` against SLAs and concurrency.
- If the environment is severely RAM-constrained: carefully evaluate Argon2id memory cost and safety under heavy load; a benchmarked BCrypt cost may be operationally safer.
- Never lower cost just to "fix timeouts" before finding the root cause: it could be CPU quotas, retry storms, missing rate limits, servlet-blocking calls on the event loop, or lack of bulkheads.
- Separate the cost of hashing during registration/password change from verification cost at login; both affect the system, though traffic patterns may differ significantly.

## 11. Specific Considerations for Spring WebFlux Authentication

Using Reactor for request handling does not make BCrypt or Argon2id non-blocking. `PasswordEncoder.matches(...)` is a synchronous CPU/RAM-bound call; running it directly on the Netty event loop with high cost can slow down many requests.

Things to verify:

1. Does your active authentication manager offload password verification to an appropriate scheduler? This behavior depends on configuration and Spring Security version; **never assume** every reactive layer automatically puts hashing on `boundedElastic`.
2. Is hashing parallelism bounded by CPU/RAM quotas? A shared `boundedElastic` pool does not automatically cap Argon2id memory per workload.
3. When the backing database/reactive user store slows down, are timeouts and backpressure configured properly?
4. Do logs/metrics distinguish user-store failures, wrong passwords, and system errors? Clients normally should not know whether a user exists.
5. Do you avoid retaining raw passwords in logs, metric tags, tracing baggage, exception messages, or payloads after authentication?

A reactive helper in a **custom service** (not replacing Spring Security's authentication manager directly) might look like:

```java
public Mono<Boolean> checkPassword(
        PasswordEncoder encoder,
        String rawPassword,
        String storedHash) {
    return Mono.fromCallable(
            () -> encoder.matches(rawPassword, storedHash))
        .subscribeOn(Schedulers.boundedElastic());
}
```

This is an illustrative method requiring imports `Mono`, `Schedulers`, and `PasswordEncoder`. It returns a publisher for the caller to compose, without `block()` or manual `subscribe()` inside handlers. Under heavy workloads, add dedicated concurrency bounds for password verification and monitor queues rather than pushing unbounded work onto the scheduler.

Never put hashes into Reactor Context as a way of "temporarily storing credentials" for downstream operators. The security context holds the authenticated **Authentication**, not raw passwords. For auditing, log events without credentials; read authenticated identity and permissions via `ReactiveSecurityContextHolder` or Spring WebFlux-provided APIs.

## 12. Common Mistakes and How to Fix Them

| Error / Symptom | Cause | Correct Approach |
|---|---|---|
| Calling `encode(password)` twice yields different hashes; assumed to be a bug | Random salt each call | Use `matches(raw, storedHash)`, never compare new hash to old hash |
| Storing `SHA-256(password)` directly | Hashing is too fast to defend passwords against offline cracking | Use BCrypt/Argon2id or a proper password KDF |
| Using `NoOpPasswordEncoder` in production | Stores/compares plaintext passwords | Use a salted, cost-configured encoder and controlled migration |
| BCrypt hash lacks `{bcrypt}` while delegate requires id | Legacy format missing prefix | Run a tested migration or register a specific compatibility path; never add reckless fallbacks |
| Adding `{argon2}` to hashes with a different profile via string replace | Mismatched routing id and algorithm parameters | Keep ids aligned with encoders, test `matches` on real hashes |
| Changing only `idForEncode` and assuming the database updated | Delegate only changes new hashes | Rehash on successful login with conditional writes |
| BCrypt ignores bytes past 72 bytes | Traditional algorithm limit | Evaluate byte length/implementation and password input policy |
| Choosing very high BCrypt strength making logins slow | Cost scales nearly exponentially | Benchmark and pick operationally viable latency/load |
| Choosing Argon2id `m=64 MiB` with too many concurrent requests | Total memory exceeds container limit | Cap concurrency, measure RSS, tune `m`/`t`/`p`/replicas |
| `ClassNotFound` when using Argon2 | Missing compatible Bouncy Castle | Add the proper dependency and inspect the dependency tree |
| Writing custom hash comparison via `String.equals` on digest | Bypasses encoder logic, salt, and format | Use `PasswordEncoder.matches` |
| Returning "user does not exist" for specific emails | Username enumeration | Use consistent login error messages and monitor rate limits |
| Hashing raw passwords on the event loop | CPU/memory blocking stalls the reactive server | Inspect authentication path, offload and bound appropriately |
| Logging passwords or hashes | Exposes credentials or data for offline cracking | Block sensitive logging, redact, audit observability |
| Raising cost without backward compatibility | Existing users cannot log in | Use `DelegatingPasswordEncoder` and phased migration |
| Using a hardcoded pepper | Secret exposed in source code | If using a pepper, manage separately in a secret manager with a rotation plan |
| Using demo users/passwords in production | Sample credentials are public | Replace with an identity store, provisioning/reset flows, and proper TLS |

## 13. Self-Check Exercises

### Exercise 1: Why Not `encode().equals()`?

A user has a `storedHash` generated yesterday. Today they log in with the exact same raw password, yet `encoder.encode(raw)` produces a different string. Should we conclude the user entered the wrong password?

**Answer:** No. Random salts make new hashes differ from old ones; you must call `encoder.matches(raw, storedHash)`. A hash also embeds the algorithm and parameters needed for verification.

### Exercise 2: BCrypt Strength 10 vs. 13

Given the same implementation/hardware and everything else equal, roughly how much more relative work does strength 13 require compared to 10?

**Answer:** The work model scales by roughly `2^(13−10) = 8` times. This is not a promise of exactly 8× HTTP latency; benchmarking is required.

### Exercise 3: Argon2id 64 MiB and Concurrent Requests

You configure `m = 65536 KiB` and allow 40 concurrent computations. Roughly how much memory is needed for those parameters alone?

**Answer:** `40 × 64 MiB = 2560 MiB ≈ 2.5 GiB`, excluding overhead. You must cap concurrent verifications or change configuration/infrastructure.

### Exercise 4: Do You Need the Raw Password to Upgrade a Hash?

The database only holds `{bcrypt}...`, and you want to store Argon2id without waiting for the user to enter a password. Can you convert the old hash directly into Argon2id?

**Answer:** No, there is no general, safe transformation from a password hash to a hash of the **raw password** using only the old hash. Rehash when the user logs in validly, changes/resets their password, or design an authenticated migration.

### Exercise 5: Modern Login with Legacy Stored Hashes

`DelegatingPasswordEncoder` has `idForEncode = "argon2@SpringSecurity_v5_8"`, while the database contains `{bcrypt}$2a$12$...`. Will `matches` work?

**Answer:** Yes, if the map includes the `bcrypt` id and a compatible BCrypt encoder. `idForEncode` only governs creating new hashes; verification relies on the stored hash's prefix. `upgradeEncoding` can signal that a profile upgrade is needed.

### Exercise 6: Protecting a Reactive Server from Overload

A login API uses high-cost Argon2id and receives unbounded traffic. Is adding `subscribeOn(Schedulers.boundedElastic())` enough?

**Answer:** No. That moves blocking work off the event loop, but CPU/RAM costs remain; you must enforce concurrency limits, rate limits, queues/backpressure, memory measurements, and monitoring. Otherwise the system can still suffer login DoS.

### Exercise 7: Does Salt Need to Be Kept Secret?

If an attacker steals a database containing hashes + salts, are all passwords immediately exposed?

**Answer:** No. Salt is not a secret and is normally stored alongside the hash. It reduces the advantage of precomputed tables and ensures identical passwords produce different hashes; attackers can still try offline guessing, so password policies, MFA, appropriate cost, and DB protection remain critical.

### Exercise 8: Why Not Use Demo Passwords as a Real Benchmark?

Demo passwords can test encoder behavior, but is a production benchmark based solely on a single simple request enough?

**Answer:** No. It must represent production hardware, container limits, concurrent workloads, the mix of legacy and modern hashes, warmup/GC, p95/p99 latency, and resilience against credential-stuffing load.

## 14. Secure Implementation Checklist

- [ ] Never store plaintext, and never put raw passwords/hashes into responses/logs/traces.
- [ ] Use an official `PasswordEncoder` with salting and an appropriate work factor.
- [ ] Store complete hash strings including `{id}` and algorithm parameters without truncating database columns.
- [ ] Choose BCrypt/Argon2id based on compatibility needs and threat model, not just popularity.
- [ ] Test passwords with Unicode and long passphrases; understand BCrypt's 72-byte boundary.
- [ ] Verify required provider dependencies for Argon2 and apply library security updates.
- [ ] Benchmark on production-like hardware/containers covering CPU, RAM, p95/p99, and concurrency.
- [ ] Enforce brute-force/credential-stuffing controls, request quotas, and bounds on concurrent heavy hashing.
- [ ] Ensure reactive authentication does not unintentionally block the event loop; verify actual schedulers and resource limits.
- [ ] Hash upgrades check `matches` first, generate a fresh salt, and persist conditionally to prevent races.
- [ ] Unmigrated users can still log in with the legacy encoder during the transition period.
- [ ] Test HTTP 401/200, legacy/modern hashes, wrong passwords, distinct salts, and upgrade signals.
- [ ] Maintain a password reset flow and secret rotation if using a pepper, without needing password decryption.

## Summary

```text
raw password  --encode (salt + cost)--> stored hash
raw password + stored hash --matches--> true/false

BCrypt:
  increasing strength by 1 => roughly doubles core work
  pay special attention to the 72-byte input limit

Argon2id:
  m = memory KiB; t = iterations; p = parallelism
  memory-hard, yet consumes RAM per concurrent verification

Spring Security:
  PasswordEncoder.encode / matches / upgradeEncoding
  DelegatingPasswordEncoder uses {id} to pick the algorithm
  migration verifies first, then rehashes on successful login

WebFlux:
  hashing remains CPU/RAM-heavy work
  preserve the reactive contract, do not block the event loop
  bound concurrency/rates and benchmark realistically
```

A strong password hash does not eliminate the need for TLS, MFA, login throttling, account management, and database security. Choosing both the right algorithm **and** sustainable operational cost creates a meaningful layer of defense.

## Official Reference Documentation

- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — PasswordEncoder API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security — BCryptPasswordEncoder API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security — Argon2PasswordEncoder API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/crypto/argon2/Argon2PasswordEncoder.html)
- [Spring Security — DelegatingPasswordEncoder API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html)
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [RFC 9106 — Argon2 Memory-Hard Function](https://www.rfc-editor.org/rfc/rfc9106)
