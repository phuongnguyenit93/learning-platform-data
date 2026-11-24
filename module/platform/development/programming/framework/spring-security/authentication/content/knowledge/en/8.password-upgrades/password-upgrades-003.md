# upgradeEncoding and When to Change Hashing Parameters

> **Scope:** Spring Security – authentication, **Password upgrades** section. This article dives into **deciding when to change password hashing algorithms or parameters**, how `PasswordEncoder.upgradeEncoding` detects outdated hashes, and how to roll out changes without breaking logins, downgrading security, or overwriting concurrent password changes. Examples use Java 17+ and Spring Boot Servlet. Numeric parameters in examples are only for observing behavior, **not recommended configurations for every production system**.

## 1. The Problem Is Not Just Increasing a Number

Suppose an application stores passwords using BCrypt cost 10. After some time in operation, the security team measures that current hardware can handle cost 12 and decides to update the hashing policy for **new passwords** and **stored passwords**. If you only change:

```java
// Before
PasswordEncoder encoder = new BCryptPasswordEncoder(10);

// After
PasswordEncoder encoder = new BCryptPasswordEncoder(12);
```

what happens?

- A new password encoded by the new encoder will have BCrypt cost 12.
- A stored BCrypt cost 10 hash can still be verified via `matches` using the cost 12 encoder, because the hash carries its own cost/salt metadata.
- **Old hashes in the database do not change on their own** when you deploy new code.
- `upgradeEncoding(oldHash)` may return `true`, yet it **does not read raw passwords and does not write to the database**.
- To rehash an old password, the application needs the **validly verified raw password** and a writer that updates the hash safely.
- Users who do not log in for a long time may retain cost 10 hashes until they change/reset their password or go through an appropriate migration workflow.

Therefore, you must distinguish **when the policy takes effect for new passwords**, **when existing hashes are upgraded**, and **when the old policy is no longer allowed for verification**.

### Three Distinct Milestones

```text
T0: Current policy is BCrypt cost 10.
        |
T1: Deploy new policy, encode NEW passwords at cost 12.
        |  DB still holds many cost 10 hashes.
        |
T2: User logs in validly -> verified raw password is available.
        |  upgradeEncoding(old hash) == true
        |  encode(raw) at cost 12, update hash conditionally.
        |
T3: Most hashes have transitioned; handle accounts that have not returned.
        |
T4: Evaluate retiring legacy algorithms/formats per policy.
```

T1, T2, T3, and T4 usually do not happen at the same time. Mistaking them for a single event can cause mass login failures or misjudge the completion progress of a password upgrade program.

## 2. The PasswordEncoder.upgradeEncoding Contract

The `org.springframework.security.crypto.password.PasswordEncoder` interface provides:

```java
String encode(CharSequence rawPassword);

boolean matches(CharSequence rawPassword, String encodedPassword);

default boolean upgradeEncoding(String encodedPassword) {
    return false;
}
```

This is a **condensed signature** for understanding the API, not a Java file to implement manually. Additional nullability annotations may be present depending on the version.

| Method | Meaning | Has raw password? | Auto-writes DB? |
| --- | --- | --- | --- |
| `encode(raw)` | Creates a new hash per encoder policy | Yes | No |
| `matches(raw, stored)` | Checks raw password against stored hash | Yes | No |
| `upgradeEncoding(stored)` | Evaluates whether stored hash needs rehashing | **No** | **No** |

Characteristics to remember:

1. `upgradeEncoding` only inspects **the stored hash** and the encoder's internal policy; it **does not authenticate** the caller.
2. The interface's default implementation returns `false`. A custom encoder that does not override it will flag nothing as needing an upgrade, even after the organization updates its policy.
3. `true` is an **upgrade recommendation**, not a data-update command and not a sign that the password was right.
4. `false` only means "this encoder does not require an upgrade under its current check"; it is not an absolute security certification of the hash.
5. For invalid formats, implementations may reject or throw errors. Never use `upgradeEncoding` as an arbitrary algorithm-guessing parser.
6. If a password is null/absent, follow the implementation/version contract; never use null values to open an authentication bypass path.

**Important distinction:** A system can force all users to change passwords under an incident policy without needing `upgradeEncoding==true`. Conversely, `upgradeEncoding==true` does not automatically mean asking the user to enter a new password; usually you only need to rehash using the verified existing password at the next login.

## 3. What Are Hashing Parameters?

"Hashing parameters" are not just the BCrypt cost. Depending on the algorithm, they can include:

- **BCrypt:** strength/log rounds, random salt, and format/version such as `$2a$`, `$2b$`, `$2y$`.
- **PBKDF2:** iteration count, PRF algorithm, salt and derived key length, encoder version choices.
- **scrypt:** work/memory and parallelization parameters, salt, output length.
- **Argon2:** memory cost, iterations, parallelism, salt, output length, version.
- **DelegatingPasswordEncoder:** ID of the encoder used to create **new** passwords, plus the mapping of legacy IDs still permitted for verification.
- **Application policy:** rehash timing, rollback conditions, maximum latency, concurrency protection, and forced-reset deadlines.

Not every encoder encodes every parameter into the same string. Not every `upgradeEncoding` implementation checks **every attribute** the security team cares about. When changing versions or algorithms, read the specific encoder contract and verify with tests on real hashes.

### BCrypt Carries Its Cost Inside the Hash

A valid BCrypt string typically begins like:

```text
$2a$10$...
$2a$12$...
```

The `...` placeholders in this block **are not valid hashes**, merely illustrating where the cost appears. The numbers `10` and `12` are log rounds. Because the hash carries its cost/salt, an encoder configured with cost 12 can still verify a cost 10 BCrypt hash without knowing any salt outside the stored string.

This is why you can change the configuration for **creating new hashes** first, then gradually upgrade legacy hashes when users log in.

### Higher Parameters Do Not Automatically Make the System Safer Overall

Increasing the work factor makes every hash/verify call more expensive. However, the system can suffer CPU exhaustion under many concurrent logins, especially with HTTP Basic sending passwords on every request. Excessive latency can also tempt operators to bypass verification steps. **Benchmarking and threat modeling are required**, rather than picking the highest configurable value.

## 4. When Should Hashing Parameters Be Changed?

There is no fixed schedule like "bump BCrypt cost every six months" that fits every system. Reasonable signals to **consider** a change include:

1. **New algorithm/cost recommendations** from trusted security sources or compliance requirements.
2. **Hardware capability changes:** CPU, RAM, machine architecture, and average load allow raising hashing cost.
3. **Increased offline risk:** the threat model assumes hashes might leak, weak passwords are easy to guess, or a legacy algorithm no longer meets targets.
4. **Infrastructure changes:** scaling to more nodes, higher authentication capacity, container CPU limits, latency budget changes.
5. **Exploitability/library versions:** security advisories involving the algorithm or its implementation.
6. **Measured real cost:** p50/p95/p99 benchmarks under load and concurrent login counts close to production.
7. **Data upgrade plan ready:** storage format, fallback read paths, writer, telemetry, and rollback are tested.
8. **Support plan for non-returning accounts:** password reset, controlled notifications, or verified migration.

A cost change should be recorded as a **versioned policy decision**: e.g., `bcrypt-policy-v2`, effective date, allowed algorithms, parameters, rationale, expected performance, rollout plan, and rules for handling remaining hashes.

### When Not to Roll Out Immediately

- The database writer does not exist yet, or can write without race protection against password resets.
- The new encoder cannot verify existing legacy hashes.
- Verification time on production hardware exceeds the p95/p99 budget or creates DoS risk.
- The system has multiple instances whose support for new/old formats is unsynchronized.
- There is no canary, telemetry, or recovery path when logins fail.
- Policies for SSO, technical/service accounts, disabled users, and long-inactive users have not been checked.

Do not push all production traffic to a new cost based on a single benchmark run on a laptop.

## 5. Distinguishing When Configuration Changes vs. When Stored Hashes Change

A change in code:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
}
```

only defines the **currently configured** encoder. It does not execute an SQL migration on the accounts table. `PasswordEncoder` is an encoding/matching object with no awareness of user repositories.

You must also separate:

- **Write policy:** which encoder/cost creates new passwords from registration/change/reset?
- **Verify compatibility:** which legacy hashes remain accepted for verification?
- **Upgrade eligibility:** during a successful authentication, which hashes should be upgraded?
- **Persistence:** how is the new hash saved without corrupting account state?
- **Retirement policy:** when do we stop accepting legacy formats and route unmigrated users to reset channels?

You can raise the **write policy** immediately at T1 while keeping **verify compatibility** during T1–T4. Avoid both extremes: turning off legacy verification too early so users cannot log in, or keeping insecure algorithms enabled indefinitely with no retirement plan.

## 6. Upgrade Decision Example with BCrypt

Suppose the old policy used cost 10 and the new policy uses cost 12:

```java
PasswordEncoder legacy = new BCryptPasswordEncoder(10);
PasswordEncoder current = new BCryptPasswordEncoder(12);

String stored = legacy.encode("demo-password");

System.out.println(current.matches("demo-password", stored)); // true
System.out.println(current.upgradeEncoding(stored));           // true

String upgraded = current.encode("demo-password");

System.out.println(current.matches("demo-password", upgraded)); // true
System.out.println(current.upgradeEncoding(upgraded));          // false
```

This is an **in-method Java snippet**, requiring imports for `PasswordEncoder` and `BCryptPasswordEncoder`, not a complete file with `main`. The boolean results are deterministic for valid BCrypt hashes.

### Do Not Downgrade If Policy Rolls Back

If a cost 12 hash exists while an instance temporarily runs a cost 10 encoder:

```java
PasswordEncoder lowerPolicy = new BCryptPasswordEncoder(10);
String strongHash = new BCryptPasswordEncoder(12)
        .encode("demo-password");

System.out.println(lowerPolicy.matches("demo-password", strongHash)); // true
System.out.println(lowerPolicy.upgradeEncoding(strongHash));          // false
```

This illustrates that a lower-cost BCrypt encoder **does not mark a higher-cost hash as needing an upgrade just because the costs differ**. However, when rolling back the new-hash creation config, newly created passwords on the older instance might be generated at a lower cost. Thus, **rollback code** must enforce its own write policy to avoid downgrading the protection you just rolled out.

### upgradeEncoding Does Not Compare Passwords Itself

This ordering is wrong:

```java
// WRONG: do not use unverified input to change a password.
if (encoder.upgradeEncoding(storedHash)) {
    repository.save(encoder.encode(passwordFromUntrustedRequest));
}
```

The variables and repository are illustrative. The wrong snippet skips `matches` and account checks; it could allow an attacker to change a password via a single failed login request.

## 7. Safe Multi-Stage Rollout Roadmap

A sample plan consists of the following phases. Stages **can be adapted to your infrastructure**; this is not a mandatory Spring Security standard.

### Phase A — Inventory and Preparation

- Inventory the distribution of algorithms, IDs, and costs **without sampling raw passwords**.
- Assess acceptable security levels and retirement deadlines for outdated algorithms.
- Benchmark the new encoder on production-like infrastructure; measure CPU, memory, p95/p99.
- Verify that all existing formats can be verified under the new configuration.
- Build `UserDetailsPasswordService`/writer or a migration flow with valid write permissions.
- Test failures, replays, concurrency, password resets, DB outages, and caching.
- Define fallback/rollback behavior that **never downgrades** already-upgraded hashes.

### Phase B — Canary and Switching Write Policy

- Deploy decoders/verifiers supporting both old and new hashes across instances before generating large volumes of hashes in the new format.
- Once compatibility is confirmed, enable the new encoder for registration/password change/reset.
- Enable lazy upgrades on a small user cohort or subset of instances **only when the backend writer is verified**.
- Monitor login failures, error types, latency, CPU, update counts, and concurrent password-change conflicts.
- Ensure every instance can verify hashes produced by any other instance.

### Phase C — Ramping Up Rehash-on-Login

- When a user logs in successfully with an old hash, `upgradeEncoding` decides whether rehashing is needed.
- `PasswordEncoder.encode(verified raw)` generates a new hash under policy.
- The writer updates the hash conditionally, avoiding overwriting password resets.
- Cache/replicas are invalidated or handled per consistency contract.
- Never use background workers granted access to plaintext passwords; plaintext should not be retained for delayed processing.

### Phase D — Handling Unmigrated Accounts

- Identify accounts still holding legacy hashes after a period of time.
- For still-acceptable hashes, continue lazy migration according to policy.
- For overly old/disallowed hashes, force a password reset through a trusted verification channel.
- Never put raw passwords, hashes, or reset tokens into logs/analytics.
- Retire legacy format support only when a recovery path exists for remaining accounts.

### Phase E — Closing the Upgrade Program

- Check remaining statistics by algorithm/cost.
- Remove unneeded legacy mappings and update runbooks/recovery procedures.
- Evaluate post-migration latency/CPU.
- Maintain a periodic schedule to review hashing policies and new advisories.

**Note:** Changing cost and upgrading millions of accounts should never be done all at once via a cron job attempting to "rehash old hashes"—without raw passwords, a job cannot produce hashes of the original passwords.

## 8. Integration Inside DaoAuthenticationProvider

For Spring Security Servlet username/password authentication, `DaoAuthenticationProvider` has key integration points:

1. `UserDetailsService.loadUserByUsername` returns a record containing the encoded password, account status, and authorities.
2. `PasswordEncoder.matches` verifies the credential.
3. Required authentication checks run; failures must never yield an authenticated `Authentication`.
4. On the success path, the provider evaluates `PasswordEncoder.upgradeEncoding(storedHash)`.
5. If an upgrade is needed and `UserDetailsPasswordService` is configured, the provider rehashes the valid raw password and calls `updatePassword(user, newEncodedPassword)`.
6. The writer must persist the new encoded hash for the right account and return the updated `UserDetails`.

Key APIs to note:

```java
DaoAuthenticationProvider provider =
        new DaoAuthenticationProvider(userDetailsService);

provider.setPasswordEncoder(passwordEncoder);
provider.setUserDetailsPasswordService(passwordWriter);
```

This is an **illustrative configuration snippet**; `userDetailsService`, `passwordEncoder`, and `passwordWriter` must be appropriate beans/instances.

**If no writer is supplied**, `upgradeEncoding` alone is insufficient to change persisted data. If you write a custom provider, do not assume Spring Security performs lazy rehashing automatically; it must be designed and tested explicitly.

### UserDetailsPasswordService Receives Encoded, Not Plaintext

Contract:

```java
UserDetails updatePassword(UserDetails user, String newPassword);
```

The name `newPassword` in the API refers to the **already-encoded password** when called by `DaoAuthenticationProvider`. The writer must not re-encode this string. Systems using JPA or a domain store must handle transactions/compare-and-set properly and return an appropriate `UserDetails`.

### Do Not Extract Credentials from Authentication After Login

`ProviderManager` erases credentials from the authenticated result. Lazy rehashing must happen at the point where the provider still holds the submitted raw password, before credentials are cleared. Never look for plaintext in `SecurityContext` or sessions to rehash later.

## 9. Spring Boot Java 17+ Example: Simulating When Cost Upgrades Happen

This example is a Spring Boot Servlet application with **Spring Web/MVC** and **Spring Security**, using an in-memory user while modeling the writer with compare-and-set. The goal is to clearly observe:

- Initially stored hash at cost 10.
- Current policy requires cost 12.
- Failed login **does not change the hash**.
- Valid login → `DaoAuthenticationProvider` invokes `UserDetailsPasswordService` and updates the hash safely.
- Next valid login **does not rehash again**.
- Output prints only booleans/costs, never password hashes or credentials.

**Setup:** Create a Java 17+ project from Spring Initializr with Spring Boot Servlet, Spring Web (on Spring Boot 4, starter `spring-boot-starter-webmvc`), and Spring Security dependencies. Pick a still-supported Spring Boot version. Create a single file **`src/main/java/com/example/policychange/PolicyChangeApplication.java`**.

```java
package com.example.policychange;

import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PolicyChangeApplication {

    public static void main(String[] args) {
        SpringApplication.run(PolicyChangeApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            PolicyAccountStore store,
            PasswordEncoder currentEncoder,
            AuthenticationManager manager) {

        return args -> {
            String before = store.storedHash();

            System.out.println("stored-cost-before="
                    + before.substring(4, 6));
            System.out.println("needs-upgrade-before="
                    + currentEncoder.upgradeEncoding(before));

            try {
                manager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "an", "wrong"));
            } catch (BadCredentialsException ex) {
                System.out.println("wrong-login=REJECTED");
            }

            System.out.println("unchanged-after-wrong="
                    + before.equals(store.storedHash()));

            Authentication authenticated = manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "an", "training-password"));

            String after = store.storedHash();
            System.out.println("authenticated="
                    + authenticated.isAuthenticated());
            System.out.println("stored-cost-after="
                    + after.substring(4, 6));
            System.out.println("needs-upgrade-after="
                    + currentEncoder.upgradeEncoding(after));
            System.out.println("password-still-matches="
                    + currentEncoder.matches("training-password", after));

            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "an", "training-password"));

            System.out.println("no-repeat-update="
                    + after.equals(store.storedHash()));
        };
    }
}

// Single account using AtomicReference to illustrate conditional updates.
// In production, replace with DB transactions / optimistic locks / CAS.
final class PolicyAccountStore
        implements UserDetailsService, UserDetailsPasswordService {

    private final AtomicReference<String> currentHash;

    PolicyAccountStore() {
        PasswordEncoder previous = new BCryptPasswordEncoder(10);
        this.currentHash = new AtomicReference<>(
                previous.encode("training-password"));
    }

    String storedHash() {
        return currentHash.get();
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        if (!"an".equals(username)) {
            throw new UsernameNotFoundException("Unknown account");
        }

        return User.withUsername("an")
                .password(currentHash.get())
                .authorities("ROLE_USER")
                .build();
    }

    @Override
    public UserDetails updatePassword(
            UserDetails user, String newEncodedPassword) {

        // Writer receives the new hash; do not encode a second time.
        boolean updated = currentHash.compareAndSet(
                user.getPassword(), newEncodedPassword);

        if (!updated) {
            throw new IllegalStateException(
                    "Password was changed by another request");
        }

        return User.withUsername(user.getUsername())
                .password(newEncodedPassword)
                .authorities(user.getAuthorities())
                .build();
    }
}

@Configuration(proxyBeanMethods = false)
class PolicySecurityConfiguration {

    @Bean
    PolicyAccountStore accountStore() {
        return new PolicyAccountStore();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12);
    }

    @Bean
    AuthenticationManager authenticationManager(
            PolicyAccountStore store, PasswordEncoder passwordEncoder) {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(store);
        provider.setPasswordEncoder(passwordEncoder);
        provider.setUserDetailsPasswordService(store);

        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager)
            throws Exception {

        return http
                .authenticationManager(manager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class PolicyDemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "principal=" + authentication.getName();
    }
}
```

### Why Does the Example Separate Responsibilities?

**`PolicyAccountStore`** is a simulated user store. It loads `UserDetails` for `DaoAuthenticationProvider` and provides `updatePassword` to swap the hash. `AtomicReference.compareAndSet(oldHash, newHash)` illustrates that the writer **does not overwrite if the stored hash has already changed**. This covers only one account and one JVM; production requires transactions/CAS at the real data store and conflict-handling rules.

**`PasswordEncoder`** is currently BCrypt cost 12. It can verify cost 10 hashes while flagging them as needing an upgrade. Rehash results have random salts and must not be logged.

**`DaoAuthenticationProvider`** has the reader, encoder, and writer attached. Simply creating `new BCryptPasswordEncoder(12)` without configuring `setUserDetailsPasswordService` will not automatically convert legacy records to cost 12.

**`ProviderManager`** executes authentication; on a wrong password it throws `BadCredentialsException`. A successful authentication also depends on account checks; the demo creates an active user to focus on hashing parameter changes.

**`CommandLineRunner`** performs before–after checks right at startup so learners observe deterministic results without printing raw hashes. By the time the server is ready for HTTP requests, the store is already upgraded to cost 12. Because data is in-memory, restarting regenerates the cost 10 hash and upgrades it again.

### Running with a Build Tool

With a Maven project created by Spring Initializr:

```bash
./mvnw spring-boot:run
```

Or Gradle:

```bash
./gradlew bootRun
```

On PowerShell, use `.\mvnw.cmd spring-boot:run` or `.\gradlew.bat bootRun`. The source imports Spring libraries, so it cannot be compiled with a bare `javac` command without classpath/dependencies.

Lines printed by `CommandLineRunner` (excluding Spring Boot logs) have the expected output:

```text
stored-cost-before=10
needs-upgrade-before=true
wrong-login=REJECTED
unchanged-after-wrong=true
authenticated=true
stored-cost-after=12
needs-upgrade-after=false
password-still-matches=true
no-repeat-update=true
```

**There is no fixed hash string in the output** because BCrypt generates a random salt. The booleans and the new cost are what the demo verifies.

Try HTTP Basic requests after the application starts:

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:training-password http://localhost:8080/me
curl -i -u an:wrong http://localhost:8080/me
curl -i http://localhost:8080/me
```

The first two successful bodies are respectively:

```text
pong
principal=an
```

The last two requests normally receive HTTP **401** per Basic authentication behavior. Error headers/bodies depend on version/configuration; Basic usually includes a `WWW-Authenticate` challenge. Basic uses Base64 rather than encrypting secrets; production must use HTTPS with no hardcoded passwords.

## 10. Why Must the Writer Prevent Overwriting Newer Passwords?

A serious hazard of lazy rehashing is **an older login request overwriting a just-completed password change/reset**.

Timeline:

```text
Time       | Login L                      | Password reset R
-----------|------------------------------|----------------------
t0         | Reads hash H1                |
t1         | Verifies old password        |
t2         |                              | User resets -> saves H2
t3         | Rehashes old password -> H3  |
t4         | Blindly writes H3            |
           |                              | H2 is overwritten: dangerous
```

If H3 overwrites H2, the password the user just reset may stop working while the old password becomes valid again. Therefore, the writer must ensure it **updates only if the source hash is still the verified hash**, or use an equivalent lock/versioning mechanism.

Illustrative conditional SQL update:

```sql
UPDATE accounts
SET password_hash = :new_encoded_hash,
    version = version + 1
WHERE account_id = :account_id
  AND password_hash = :old_verified_hash;
```

This is illustrative SQL, not a default Spring Data query. Check the affected row count. If it is 0, the hash changed between read and write; do not retry writing H3. With JPA, use `@Version`/optimistic locking or row locks matching your transaction and isolation level.

### Do Not Use Request-Supplied Usernames to Decide Which Record to Write

`UserDetailsPasswordService.updatePassword` receives the `UserDetails` used by the provider. In systems with immutable user IDs, the writer should map to a **trusted internal account ID**, never reading `userId` from a query/header to update a hash. Multi-tenant systems must verify the exact identity scope; a username may only be unique within a single tenant.

### Do Not Hash an Encoded Value Twice

`newEncodedPassword` is already a hash created by the encoder. Wrong:

```java
// WRONG when newEncodedPassword is already encoded:
account.setPasswordHash(encoder.encode(newEncodedPassword));
```

Doing so hashes the hash string itself, causing real passwords to fail matching. Keep the contract clear: in a user-chosen password change flow, call `encode(rawNewPassword)`; in `UserDetailsPasswordService`, **save the supplied `newEncodedPassword` as-is**.

## 11. Changing Algorithms or Formats: DelegatingPasswordEncoder

A system may have used multiple algorithms or encoder versions over time. `DelegatingPasswordEncoder` selects the encoder from the **`{id}`** prefix:

```text
{id}encodedPassword

Shape examples:
{bcrypt}$2a$10$...
{pbkdf2}...
{scrypt}...
```

The ellipses only illustrate formatting. Never use those values as real hashes.

`idForEncode` determines the **new** hash creation format. `matches` uses the ID embedded in the stored hash to locate the corresponding encoder. This lets you deploy the ability to **read legacy hashes** before starting to write new ones.

An illustrative configuration:

```java
PasswordEncoder delegating = new DelegatingPasswordEncoder(
        "bcrypt-v2",
        Map.of(
                "bcrypt-v1", new BCryptPasswordEncoder(10),
                "bcrypt-v2", new BCryptPasswordEncoder(12)));
```

This is a **code snippet** requiring imports for `PasswordEncoder`, `DelegatingPasswordEncoder`, `BCryptPasswordEncoder`, and `java.util.Map`. If legacy data has the `{bcrypt-v1}` prefix, the mapping allows verifying it; new hashes will start with `{bcrypt-v2}`. These IDs are **illustrative application conventions**, not Spring Security defaults. You can also keep the same `bcrypt` ID and swap the child encoder's strength, in which case the child BCrypt's `upgradeEncoding` checks the cost.

### Why Roll Out the Decoder Before the Encoder?

If server A starts producing `{bcrypt-v2}` while server B only understands `{bcrypt-v1}`, a user can log in on A and then fail on B due to an unrecognized format. During rolling or blue/green deployments, ensure every instance serving traffic has **both new and old verification capability** before starting to write the new format.

### What About Hashes Without {id}?

An older database may store `$2a$10$...` directly. `DelegatingPasswordEncoder` cannot infer the ID when the prefix is missing; by default `matches` may throw `IllegalArgumentException` when no mapping is found. You can plan a prefix-tagging pass on **hashes verified to match the format** or a bounded legacy decoder with a deprecation schedule. Never default to treating unprefixed strings as plaintext.

### Do Not Enable Weak Fallbacks to Rescue Logins

Extending a decoder to "compare plaintext if no ID is recognized" can introduce a severe vulnerability. Never use `NoOpPasswordEncoder` for production data without an approved migration. When a legacy algorithm is no longer safe, **forcing a password reset** is often the right choice over continuing to accept all legacy hashes.

## 12. When Does upgradeEncoding Not Reflect the Entire Policy?

`upgradeEncoding` is a useful API, but it has scope limits:

- The current encoder may only evaluate the **work factor** without enforcing all security policies.
- Checking for compromised credentials or requiring MFA is not `upgradeEncoding`'s responsibility.
- A disabled/locked user must not be treated as eligible to log in just because their hash needs upgrading.
- A policy requiring password resets due to suspected account compromise is a separate workflow, not merely bumping cost.
- A hash with a higher cost but created by an algorithm/implementation no longer accepted must be evaluated under different criteria.
- A custom encoder with default `upgradeEncoding=false` can miss migration needs if not overridden.

Therefore, define the **source of truth for password hashing policy** in versioned configuration, alongside input tests for old/new hashes and mandatory-reset cases. Never rely solely on `upgradeEncoding=true` counts to claim all passwords meet organizational requirements.

## 13. Benchmark Before Changing Parameters

An operations team should measure password verification on production-like hardware under realistic workloads:

| Item | What to measure/control |
| --- | --- |
| Verify/hash latency | Mean, p95, p99 by cost/algorithm |
| Concurrent load | Simultaneous logins, CPU, memory, queue depth |
| HTTP Basic vs. sessions | Basic may verify passwords on many requests |
| Tokens/SSO | Not every request needs password hashing |
| Lazy rehash cost | An upgrade login can cost **legacy verify + new encode** |
| Scaling | Container CPU limits and cold starts |
| Rate limiting | Prevent attackers from causing CPU exhaustion |
| Database writes | Hash updates, locks/transactions, cache invalidation |
| User experience | Login duration and session-timeout errors |
| Rollback | Can upgraded hashes still be verified? |

**Latency on a login requiring an upgrade differs from a normal login.** If rehashing runs synchronously during authentication, a user's first login after rollout pays the extra cost of encoding the new hash and writing to the DB. Measure the frequency of such logins in a canary.

To pick a cost, you do not need to log 10,000 raw passwords or benchmark directly on production accounts. Use synthetic test data, isolate the hashing workload, and stay cautious across multi-tenant or heterogeneous CPU architectures.

### Should Rehashing Be Asynchronous?

Do not simply "toss raw passwords onto a queue" to upgrade later; plaintext could persist longer, get logged, or traverse under-protected services. The safer default is rehashing at the authentication boundary where the verified raw password already exists, persisting within a controlled transaction/operation. If choosing a specialized async design, conduct a thorough review of security, secret lifecycle, ordering, and conditions preventing stale overwrites over newer resets.

## 14. Measuring Migration Progress Without Exposing Hashes

An upgrade program needs visibility into:

- Account ratios by algorithm/prefix/cost before and after rollout.
- Count of `upgradeEncoding=true` evaluations **within successful authentications**.
- Successful writer updates, CAS conflicts, and database errors.
- Logins rejected due to incompatible hashes.
- Verify + upgrade latency and timeout rates.
- Ratio of long-inactive accounts still holding legacy hashes.
- Mandatory password reset volume and completion rates.

To measure this, you only need algorithm/cost metadata or policy names—never push **raw passwords or full hashes** into analytics logs. Never log Basic `Authorization` headers, session cookies, or bearer tokens. Stored hashes remain sensitive data because they enable offline cracking if leaked.

A safer conceptual log format:

```json
{
  "event": "password_hash_upgrade",
  "policy_from": "bcrypt-cost-10",
  "policy_to": "bcrypt-cost-12",
  "result": "updated",
  "request_id": "correlation-id"
}
```

This is a **structural example**, not a mandatory log schema; `correlation-id` should come from an appropriate tracing mechanism. Detailed per-account auditing belongs only in access-controlled systems, with proper security-data retention considerations.

### Distinguishing Writer Outcomes

| Outcome | Meaning | Appropriate handling |
| --- | --- | --- |
| `updated` | Hash updated from expected-old to new | Success; invalidate cache if needed |
| `not_needed` | Hash already satisfies policy | No write |
| `concurrent_change` | Hash changed between read and write | Do not overwrite; classify/investigate |
| `storage_unavailable` | DB unavailable | Do not report upgraded; handle auth per policy |
| `unsupported_hash` | Format/algorithm unsupported | No weak fallback; route to reset/migration |
| `auth_failed` | Password or auth conditions failed | **Do not rehash** |

Never lump `auth_failed` and `storage_unavailable` into the same "wrong password" bucket in internal telemetry, even though public responses must avoid leaking account details.

## 15. Rollback and Cross-Version Compatibility

Rolling back code must never mean **rolling back password hashes** or downgrading cost. When reverting to a prior application version, ensure that version can still read hashes created by the new rollout.

### Scenarios to Test

**Scenario A — BCrypt cost bump only:** an older instance running BCrypt cost 10 can normally still `matches` stored cost 12 hashes. However, if the old instance still creates new passwords at cost 10, block downgrade writes or enforce an independent write policy.

**Scenario B — Changing {id}:** an older version lacking the `{bcrypt-v2}` mapping will fail to match new hashes. Deploy decode compatibility first, or roll back to an older version **that already supports the new decoder**.

**Scenario C — Full algorithm switch:** never assume an old decoder supports new Argon2/PBKDF2 formats. Test data compatibility, rollout sequence, and password-reset recovery if support is missing.

**Scenario D — Concurrent password change and rehash:** an older writer without CAS can overwrite password resets. Never enable rehashing on instances lacking concurrency guards.

**Scenario E — Stale cache:** an instance reads an old hash from a replica/cache while the primary already upgraded it. Unnecessary re-rehashing can trigger extra writes, conflicts, or concurrency bugs. Establish clear invalidation and read-consistency strategies.

### Things Not to Do During Rollback

- Lower the encoder cost and **rehash all strong hashes back down to weak ones**.
- Arbitrarily strip `{id}` prefixes, leaving decoders unable to identify algorithms.
- Disable `PasswordEncoder.matches` and use "temporary" plaintext comparison.
- Disable account status checks or MFA to work around login errors.
- Reset user passwords to a default password or store raw passwords for recovery.
- Keep writing new-format hashes while part of the fleet cannot verify them.

## 16. Which Users Might Not Upgrade via Login?

Not every account gets an opportunity to supply a raw password:

- **Long-inactive accounts:** old hashes remain until the user logs in or resets.
- **Disabled/locked accounts:** a rejected login must never issue a session or update a hash as if authentication succeeded.
- **SSO/OIDC accounts:** the application may not own passwords; the identity provider manages their hashing.
- **API-token accounts:** bearer token requests carry no user password, so there is no raw password to rehash.
- **Service accounts:** may use client secrets/certificates instead of user passwords; need separate credential policies.
- **Accounts with overly weak/unreadable legacy hashes:** require a verified password reset program.
- **Users who just reset their password:** the new password is already encoded under current policy; no legacy hash upgrade needed.
- **Multi-tenant:** migration priorities and allowed algorithms may vary per tenant, without crossing tenant authorization/lock boundaries.

Never write a batch job that reads `oldHash` and calls `encode(oldHash)` to "upgrade everyone"; that hashes **the old hash string**, not the user's password. When no valid raw password is available, rely on future logins or a verified reset/re-issuance process.

## 17. Testing Matrix When Changing Policy

| Test | Setup | Expected result |
| --- | --- | --- |
| BCrypt compatibility | Stored cost 10, verifier cost 12 | `matches(raw, oldHash)=true` |
| Upgrade signal | Stored cost 10, policy cost 12 | `upgradeEncoding(oldHash)=true` |
| Already upgraded | Stored cost 12, policy cost 12 | `upgradeEncoding(newHash)=false` |
| Wrong password | Different raw password | Not authenticated, **no new hash written** |
| Right password + writer | Valid old hash | Rehashed and persisted at cost 12 |
| Subsequent valid login | Stored already cost 12 | No repeated update |
| No writer | Provider only has encoder | Cannot assume new hash is persisted |
| Locked account | Password may be right | No session issued; no upgrade on rejected login |
| Concurrent reset | Reset wrote H2 before lazy rehash H3 | H2 is not overwritten |
| CAS failure | Source hash changed | Does not blindly retry with old raw |
| Mixed fleet | New instance creates new format | Every traffic-serving instance can verify |
| Unprefixed hash | Delegating without fallback | Does not auto-accept plaintext |
| Unknown algorithm | Unmapped stored ID | Fail closed / valid recovery |
| DB writer error | Auth valid but update fails | Does not report update success; follows failure policy |
| Inactive user | Old hash remains | Clear reset/inactive-account plan |
| JWT-only request | No raw password | No automatic rehash |
| High cost under load | Many concurrent logins | Latency/CPU within bounds or safe rollback |
| Username/email change | Immutable account ID | Writer updates right account without trusting user-supplied keys |
| Log inspection | Upgrade event occurs | No passwords/hashes/tokens logged |
| Security review | Dependency changes | Check corresponding APIs/advisories |

### Simple Check Without Starting a Web Server

This Java snippet requires importing `PasswordEncoder`/`BCryptPasswordEncoder` inside a method; it can run in a test project with Spring Security Crypto:

```java
PasswordEncoder v1 = new BCryptPasswordEncoder(10);
PasswordEncoder v2 = new BCryptPasswordEncoder(12);

String oldHash = v1.encode("pass");
boolean valid = v2.matches("pass", oldHash);
boolean needsUpgrade = v2.upgradeEncoding(oldHash);

String newHash = v2.encode("pass");
boolean upgradedMatches = v2.matches("pass", newHash);
boolean stillNeedsUpgrade = v2.upgradeEncoding(newHash);

System.out.println(valid);
System.out.println(needsUpgrade);
System.out.println(upgradedMatches);
System.out.println(stillNeedsUpgrade);
```

Verifiable output:

```text
true
true
true
false
```

Never compare raw hashes against a fixed string because salts are randomly generated. Integration tests should also verify the full provider/writer path and durable persistence in the user store.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Changing cost in a bean and assuming the whole DB upgraded | Old hashes remain | Lazy rehash/writer and metrics |
| Treating calling `upgradeEncoding` as upgrading the password | Nothing gets updated | `encode(verified raw)` + writer |
| Rehashing input password before `matches` | Attacker can overwrite someone else's password | Update only after valid authentication |
| Encoding old hash to switch algorithms | Hash of a hash; original password fails to match | Rehash from verified raw or reset |
| Using `encode(raw).equals(stored)` | Salt breaks equality | Use `matches(raw, stored)` |
| Picking max cost without benchmarking | CPU saturation, slow logins/DoS | Measure p95/p99 and resources |
| Emitting new format before fleet has decoder | Some instances fail verification | Decode-first deployment |
| Missing `UserDetailsPasswordService` | Lazy upgrades never persist | Configure writer properly |
| Writer re-encodes `newEncodedPassword` | Password double-hashed | Save encoded string intact |
| Blind write during concurrent reset | New reset password gets overwritten | Transactions/CAS/optimistic locking |
| Treating `upgradeEncoding=false` as absolute security | Misses policy/advisories | Security reviews and policy versioning |
| Custom encoder forgets to override upgrade | Never upgrades | Implement and test explicitly |
| Leaving plaintext/NoOp fallback in production | Opens weak/bypass path | Bounded migration or reset |
| Cost rollback downgrades new hashes | Weakens protection | Rollback code has non-downgrading write policy |
| Forgetting long-inactive accounts | Legacy hashes linger indefinitely | Verified reset or deadline |
| Logging passwords/hashes for telemetry | Sensitive data leak | Log metadata and aggregate metrics only |
| Expecting JWT requests to upgrade hashes | No raw password present | Login/password reset are the right places |
| Using request username to update hash | Wrong account/tenant, potential data leak | Trusted internal ID |
| Disabling account lock to rehash | Bypasses authentication policy | Never upgrade on rejected logins |
| Not testing malformed hashes | Runtime crashes or unsafe fallbacks | Validate format, fail closed |

## 19. Self-Check Knowledge

**Question 1.** When replacing `new BCryptPasswordEncoder(10)` with `new BCryptPasswordEncoder(12)`, have all DB hashes become cost 12?  
**Answer:** No. New passwords follow the new policy, while old hashes need rehashing on valid login or appropriate reset/migration.

**Question 2.** Why can a cost 12 encoder still `matches` a cost 10 BCrypt hash?  
**Answer:** A BCrypt hash embeds its salt and cost, allowing the verifier to compute using the old hash's parameters.

**Question 3.** Does `upgradeEncoding(oldHash)==true` verify that the user's password is right?  
**Answer:** No. The method takes no raw password; it only evaluates the hash against policy.

**Question 4.** When is a valid raw password available for rehashing?  
**Answer:** During a successful authentication flow or an authorized password change/reset flow.

**Question 5.** Why can't you run a batch job doing `encode(oldHash)`?  
**Answer:** Because it hashes the `oldHash` string rather than the original password; users would not be able to log in with their old password.

**Question 6.** Without `UserDetailsPasswordService` configured, does enabling `upgradeEncoding` save new hashes?  
**Answer:** No. You need a writer or an equivalent durable persistence mechanism.

**Question 7.** Why deploy decoders that understand the new hash before writing the new format across a fleet?  
**Answer:** So every instance can verify hashes produced by new instances, avoiding intermittent login failures.

**Question 8.** Why is CAS/optimistic locking important during rehashing?  
**Answer:** So a rehash from a login reading an old hash does not overwrite a fresh password reset.

**Question 9.** Should cost be raised every month?  
**Answer:** There is no universal schedule; change it when security review, benchmarks, and rollout planning show it is appropriate.

**Question 10.** If a cost 12 hash hits an instance temporarily running cost 10, must it be downgraded to cost 10?  
**Answer:** No. Verifying a stronger hash normally does not ask for rehashing; rollbacks must avoid creating weak new hashes.

**Question 11.** Why doesn't an OIDC-only account get its internal hash upgraded automatically?  
**Answer:** The application has no raw password to rehash; password storage belongs to the identity provider if it manages credentials.

**Question 12.** Why might the first login after rollout be slower?  
**Answer:** It may have to verify the old hash, encode the raw password at the new cost, and write to storage; measure latency/capacity.

**Question 13.** With `DelegatingPasswordEncoder`, what does `{id}` affect?  
**Answer:** The ID picks the decoder for stored hashes; `idForEncode` picks the encoder used for new hashes.

**Question 14.** Does `upgradeEncoding=false` replace reviewing advisories and password policies?  
**Answer:** No. It only reflects the current encoder's logic.

## Conclusion

`upgradeEncoding` is **the bridge between current hashing policy and hashes stored under older policies**, yet it only returns a decision; it does not hash, authenticate callers, or write to the DB. "When to change hashing parameters" must be viewed across multiple milestones: choosing the new policy, opening compatibility, creating new hashes, rehashing when users log in validly, and retiring legacy algorithms.

A sound rollout includes **evaluating protection and performance**, **preserving legacy verification for as long as needed**, **rehashing only with verified raw passwords**, **conditional writer updates**, **progress tracking and non-downgrading rollbacks**, plus a reset path for accounts that never return to log in.

**Rule to remember:** *Changing the encoder does not change stored data; `upgradeEncoding` only signals the need; only a valid authentication flow and a safe writer turn legacy hashes into new hashes.*

### Official References

- [Spring Security — PasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security — BCryptPasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security — DelegatingPasswordEncoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — UserDetailsPasswordService API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
