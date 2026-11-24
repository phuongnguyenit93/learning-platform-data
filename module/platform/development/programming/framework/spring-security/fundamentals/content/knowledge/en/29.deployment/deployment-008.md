# Password Hashing Performance and Latency of External Authentication Services

## 1. Slow logins do not necessarily share the same root cause

When deploying a Java application with Spring Security, an authentication request may be slow due to **intentionally expensive password hashing**, or due to **network waits and external authentication services**. These two sources of latency have very different causes and fixes:

- Hashing passwords with `bcrypt`, `PBKDF2`, `scrypt`, or `Argon2` consumes CPU and/or memory **to raise the cost of guessing passwords if hashes are leaked**. Never replace them with fast hashes or plaintext passwords just because login is slow.
- Calling LDAP, OIDC token endpoints, an IdP, OAuth2 opaque-token introspection, or user-info services can take time due to DNS, TLS, networking, connections, queues, IdP load, caching, or retries. That is **external-dependency latency**.
- APIs verifying digitally signed JWTs can normally **validate tokens locally** using cached public keys. Do not assume every Bearer request must call the IdP.
- Apps using **sessions after form login** typically do not hash passwords on every request; passwords are verified only at login or re-authentication. That is why short-lived sessions/tokens drastically cut hashing load compared to per-request HTTP Basic authentication.

Learning objectives:

1. Measure and analyze `PasswordEncoder.encode` / `matches` cost on real infrastructure.
2. Pick a **work factor** strong enough within safe operational limits, rather than chasing an arbitrary number.
3. Estimate concurrent load and avoid CPU/memory bottlenecks or self-inflicted DoS on login endpoints.
4. Distinguish latency across OIDC login, JWT validation, remote introspection, and LDAP.
5. Configure timeouts, concurrency limits, circuit breakers, retries, and caches **without weakening authentication/revocation rules**.
6. Use metrics, secret-scrubbed tracing, and load tests to optimize while keeping accounts protected.

Example scope: **Java 17+, Spring Boot 3.x, Spring Security 6.x**. For newer major Spring Boot/Security releases, re-check APIs and defaults. All timings in tables below are **illustrative figures or formulas**, not benchmark results on your hardware.

## 2. Diagram the exact flow before measuring

### 2.1. Application with local password authentication

```text
Client -> POST /login
    -> network/TLS/web filter
    -> query account in DB/cache
    -> PasswordEncoder.matches(rawPassword, storedHash)
    -> check account locked/disabled and other policies
    -> create Authentication and valid session/token
    -> return response/redirect
```

Total user-perceived latency can be broken down as:

```text
T_login ≈ T_network + T_queue + T_db + T_password_match
        + T_policy + T_session + T_response
```

This is a **decomposition for measurement**, not an exact sum where stages overlap. If `T_password_match` dominates, cutting DB queries will not speed up login significantly. If CPU sits idle while responses lag, measure queues, the database, or networking before touching the work factor.

### 2.2. Web login via OIDC

```text
Browser -> Spring Security OAuth2 Login client
       -> redirect to IdP (DNS, TLS, network)
       -> user enters credentials/MFA or uses SSO session at IdP
       -> browser returns to app with authorization code
       -> app calls token endpoint and validates response/ID token
       -> app maps identity -> account, authorities, and session
       -> browser receives response
```

Latency here includes **user interaction time** and multiple hops across browser, IdP, and application. Never measure OIDC login with one HTTP call to an internal endpoint and call it end-to-end latency.

### 2.3. API verifying Bearer tokens

```text
JWT access token:
  Client -> API -> parse/verify JWT + validate claims
                -> use public key from JWKS cache when available
                -> authorization -> response

Opaque token via introspection:
  Client -> API -> HTTPS to IdP introspection endpoint
                -> verify token active, scopes/claims
                -> authorization -> response
```

Key difference: JWT validation normally **needs no remote introspection per request** once appropriate keys are cached; opaque-token introspection in Spring Security's default setup **calls an external endpoint to verify Bearer tokens**. Adding caching or specialized providers alters this profile, so never assume caching is present without checking.

## 3. Why must password hashing be intentionally expensive?

Passwords must never be stored in plaintext or plain `SHA-256(password)`. Fast integrity hashes let attackers test huge candidate volumes if a hash database is stolen.

Adaptive password-hashing functions use a **work factor**: raising it makes checking each candidate more expensive. That adds cost for the real server at login, while making offline password-guessing attacks far costlier.

| Algorithm | Key characteristics | Deployment considerations |
| --- | --- | --- |
| `bcrypt` | Adaptive password hash; cost scales with cost/strength | Benchmark cost on real CPU; watch bcrypt input/Unicode limits when designing password policies |
| `PBKDF2` | Iterated key derivation function; widely supported | Select iterations/PRF per policy; fits certain compliance mandates |
| `scrypt` | Intentionally memory-hard | Budget RAM against concurrent verifications |
| `Argon2id` / `Argon2` | Designed to resist parallel hardware attacks; time/memory/parallelism parameters | Measure **both CPU and RAM**; Spring Security/implementation versions differ in dependencies and parameters |

Never implement low-level hashing or random salting yourself when the framework provides `PasswordEncoder`. Every password hash should carry an encoder-managed salt/randomness; **hashing the same password twice should not normally produce identical strings**.

### Work factor is not "strong vs. weak passwords"

Long/unpredictable passwords, breached-password checks, MFA, and login rate limits are separate layers. A 1-second hash will not save an account with a trivial password against online guessing if the API lacks rate limiting; conversely, MFA does not replace proper hash storage.

Spring Security 6.5 documentation recommends **tuning the work factor so verifying a password takes roughly one second on your target system** as a security reference point—not a mandatory SLA for every organization. Balance that guidance against hardware, RAM, real load, p95/p99 targets, resilience, and policy. Start by benchmarking in a production-equivalent environment instead of copying a single cost value from a developer laptop.

### Why slower hashing is not always better

If one `matches` call saturates a CPU core for a full second, 10–20 simultaneous login requests can build long queues, trigger timeouts, starve the API, or lock out valid users. With scrypt/Argon2, **RAM per concurrent verification** is also bounded. Raising the work factor must pair with capacity planning and login traffic protection.

## 4. Spring Security PasswordEncoder and hash formats

A common setup:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
```

This is a **snippet for a Spring `@Configuration` class**, requiring imports for `PasswordEncoder`, `PasswordEncoderFactories`, and `@Bean`. `DelegatingPasswordEncoder` prefixes hashes with an algorithm ID, e.g.:

```text
{bcrypt}$2a$...hash...
{pbkdf2@SpringSecurity_v5_8}...hash...
{scrypt@SpringSecurity_v5_8}...hash...
```

The strings above are **illustrative shapes, not valid login hashes**. The ID identifies which decoder handles `matches`; when upgrading policies, the app can still verify legacy hashes and upgrade them when appropriate.

Notes:

- `DelegatingPasswordEncoder` **does not magically make BCrypt cheaper**; every algorithm pays its real cost.
- `new BCryptPasswordEncoder(11)` uses strength 11, **not a guarantee that 11 is always strong enough or fast enough**. Cost 10 is the reference default in many Spring Security 6.x releases; verify the version you run.
- Every `encode` on signup/password change costs compute, and every `matches` on login costs compute too. **Never re-encode every user's password at application startup.**
- Never compare hashes with `storedHash.equals(encoder.encode(rawPassword))`, because random salts make outputs differ. Always call `encoder.matches(rawPassword, storedHash)`.
- Never patch missing `{id}` hashes by leaving `NoOpPasswordEncoder` as a production fallback. Build a bounded, tested legacy-hash migration plan.
- When raising the work factor, use controlled password upgrades (e.g., `PasswordEncoder.upgradeEncoding` with `UserDetailsPasswordService` where suitable) instead of forcing users to supply plaintext for bulk re-hashing.

## 5. Runnable Java 17+ example: timing encode and matches

We build a **command-line Spring Boot application** with no web server to measure just the algorithm itself, avoiding a public benchmark API that could be abused.

Initialize a Spring Boot 3.x, Java 17+, Gradle project via Spring Initializr with the core starter, then add Spring Security Crypto. Inside `build.gradle` with Initializr's Spring Boot and dependency-management plugins already present, ensure these dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.security:spring-security-crypto'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

If Initializr generated duplicate dependencies, **keep a single declaration**. This is the `dependencies`/`test` block, not the entire build script.

Complete Java file:

```text
src/main/java/demo/hashbench/PasswordHashBenchApplication.java
```

```java
package demo.hashbench;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class PasswordHashBenchApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordHashBenchApplication.class, args);
    }

    @Bean
    ApplicationRunner runHashBenchmark() {
        return args -> {
            // Do not use a real password; local fixture only.
            String samplePassword = "local-test-password-only!";

            // Strength=11 is for benchmarking only; must be tuned.
            PasswordEncoder encoder = new BCryptPasswordEncoder(11);
            String initialHash = encoder.encode(samplePassword);

            boolean right = encoder.matches(
                samplePassword, initialHash
            );
            boolean wrong = encoder.matches(
                "not-the-password", initialHash
            );

            // Warm-up to reduce JVM/library initialization noise.
            for (int i = 0; i < 2; i++) {
                encoder.matches(samplePassword, initialHash);
            }

            List<Long> encodeNanoseconds = new ArrayList<>();
            List<Long> verifyNanoseconds = new ArrayList<>();

            for (int i = 0; i < 12; i++) {
                long encodeStart = System.nanoTime();
                String hash = encoder.encode(samplePassword);
                long encodeEnd = System.nanoTime();

                long verifyStart = System.nanoTime();
                boolean matches = encoder.matches(
                    samplePassword, hash
                );
                long verifyEnd = System.nanoTime();

                if (!matches) {
                    throw new IllegalStateException(
                        "Hash verify did not match!"
                    );
                }

                encodeNanoseconds.add(
                    encodeEnd - encodeStart
                );
                verifyNanoseconds.add(
                    verifyEnd - verifyStart
                );
            }

            Collections.sort(encodeNanoseconds);
            Collections.sort(verifyNanoseconds);

            System.out.println("algorithm=bcrypt");
            System.out.println("strength=11");
            System.out.println("correctMatches=" + right);
            System.out.println("wrongMatches=" + wrong);
            printStats("encode", encodeNanoseconds);
            printStats("verify", verifyNanoseconds);
        };
    }

    private static void printStats(
            String phase, List<Long> sorted) {

        System.out.printf(
            Locale.ROOT,
            "%s_p50_ms=%.1f%n",
            phase,
            percentileMilliseconds(sorted, 0.50)
        );
        System.out.printf(
            Locale.ROOT,
            "%s_p95_ms=%.1f%n",
            phase,
            percentileMilliseconds(sorted, 0.95)
        );
    }

    private static double percentileMilliseconds(
            List<Long> sorted, double fraction) {

        int index = Math.max(
            0, (int) Math.ceil(fraction * sorted.size()) - 1
        );

        // Measurements are in nanoseconds; convert to milliseconds.
        return sorted.get(index) / 1_000_000.0;
    }
}
```

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.application.name=password-hash-bench
```

Run from the Gradle project root:

```bash
./gradlew bootRun
# Windows PowerShell:
# .\gradlew.bat bootRun
```

**Deterministic output lines** when the encoder works properly:

```text
algorithm=bcrypt
strength=11
correctMatches=true
wrongMatches=false
```

Beyond those lines, the app prints Spring Boot startup logs and four timing lines: `encode_p50_ms`, `encode_p95_ms`, `verify_p50_ms`, and `verify_p95_ms`. **There is no fixed timing stdout** because results depend on CPU, JVM, JIT, concurrent load, and environment. Format example:

```text
encode_p50_ms=<actual measured value>
encode_p95_ms=<actual measured value>
verify_p50_ms=<actual measured value>
verify_p95_ms=<actual measured value>
```

These are placeholders illustrating output format, **not measured numbers**. The benchmark uses 12 samples for readability, **far too few for reliable production p95 or p99 claims**. Publishing capacity numbers requires larger sample counts, proper warm-up, multiple runs, and realistic concurrent load.

### Why measure encode and verify separately?

- `encode` runs on signup, password change, or hash upgrade; its cost affects throughput of those flows.
- `matches` runs during password authentication; its cost directly affects login latency and CPU load.
- For current algorithms/hashes, both are typically the same order of cost, yet **never rely on one `encode` measurement to predict every `matches` call**. Stored hashes with differing parameters, different hardware, or concurrent requests alter results.

**Never benchmark with real passwords** or log hashes/credentials. In production, never add a public `/benchmark-password` endpoint—attackers can turn it into a DoS vector.

## 6. From single-call timing to concurrent capacity

One password verification time on an idle machine is not system capacity. Consider:

- Actual **vCPUs allocated** to the container/VM (quotas/limits may be lower than host specs).
- CPU cost per verification; memory-hard algorithms also consume RAM.
- Concurrent login requests plus CPU usage from other endpoints and DB work.
- Thread pool and queue sizes, DB connection pools, and GC headroom.
- Credential-stuffing attacks spiking login attempts without **increasing valid users**.

### Estimating CPU via formula

If verification is mostly CPU-bound taking roughly `T_cpu` seconds and arrival rate is `lambda` verifications/second, CPU demand is approximately:

```text
CPU core-seconds per second ≈ lambda * T_cpu

ILLUSTRATIVE example:
  lambda = 20 password verifications / second
  T_cpu  = 0.25 CPU seconds / verification
  demand = 20 * 0.25 = 5 CPU core-seconds / second

An instance with only 4 vCPUs cannot sustainably handle
5 core-seconds/second concurrently for password verification alone
without architectural tuning, load distribution, or traffic reduction.
```

This is an approximation omitting overhead, memory bottlenecks, context switching, and other work. If `matches` takes 1 CPU second, 20 logins/second demands 20 CPU core-seconds per second. Scale instances/resources, cut unnecessary verifications, or redesign the flow; **never drop the work factor below password-policy requirements**.

### Little's Law when waiting on external services

With request rate `lambda` and average time spent processing/waiting `W`, average in-flight requests are roughly:

```text
L = lambda * W

Example:
  100 introspection calls/second
  average wait 0.15 seconds per call
  L ≈ 100 * 0.15 = 15 in-flight calls

If p99 rises to 2 seconds during an incident,
in-flight calls and queues can grow rapidly,
especially when clients omit timeouts/limits.
```

**Distinguish CPU saturation from network waits:** 15 waiting remote calls do not equal 15 busy CPU cores. They still hold connections, memory, request slots, and threads if using a blocking HTTP client. Monitor CPU, threads, connection pools, and queues together.

### Two dangerous queue types

1. **CPU-bound hash verification:** enlarging thread pools infinitely does not make CPUs hash faster. It makes more tasks contend for CPU and inflates tail latency.
2. **I/O-bound external authentication:** opening too many connections or retrying without bounds can overwhelm the IdP and your own app, causing cascading failures.

Real systems need bounded concurrency, bounded queues, admission control, and rate limiting. Under overload, failing fast with clear policy-driven rejections is better than letting requests queue indefinitely and time out together.

## 7. Work factor and hash upgradability

Raising cost is both a **security and performance policy change**, not just tweaking a number:

```java
// Illustrates configuring a dedicated encoder, not a
// standalone program.
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
}
```

Moving from cost 10 to 12 increases bcrypt compute exponentially; **exact milliseconds cannot be predicted** without benchmarking. For memory-hard algorithms, changing memory/parallelism parameters can also push containers into OOM under concurrency.

Recommended change workflow:

1. Record policy version, algorithm/hash format, and current cost.
2. Benchmark on production-like hardware/staging under both normal and peak loads.
3. Measure login p50/p95/p99, CPU/RAM, queue depth, error rates, and autoscaling behavior.
4. Run bounded load tests covering unknown users, wrong passwords, and credential stuffing.
5. Roll out gradually; watch CPU/latency spikes and keep a config rollback plan **that does not break verifying already-upgraded hashes**.
6. Leverage `DelegatingPasswordEncoder`'s `{id}` prefix / `upgradeEncoding` to save a re-encoded hash **after the user proves the right password**, if supported by your app.
7. Never store plaintext passwords "to rehash later", never temporarily enable `NoOpPasswordEncoder`, and never skip authentication steps under overload.

### Notes on the upgrade path

When old hashes remain valid yet use a lower work factor, the app can verify the old hash in its legacy format and upgrade it upon successful login. Guard against races when concurrent requests or password changes in another session occur.

You cannot securely upgrade an old hash without the right input: without the plaintext password, you cannot simply "re-hash the hash" into an equivalent password hash. `UserDetailsPasswordService` can persist upgraded hashes during Spring Security's upgrade workflow; verify how your project's actual provider uses that interface.

### Timing with non-existent accounts

If the server returns "user not found" immediately without running an equivalent verification, attackers can use timing differences to enumerate usernames. Some authentication providers mitigate timing differences, but never assume custom code already does. Use generic error messages and anti-enumeration techniques; keep in mind that dummy hash verification also consumes CPU and must be included in capacity plans.

## 8. Pay password-hashing cost only when truly necessary

Spring Security documentation stresses that verifying expensive passwords **on every request** degrades performance. After proving a long-term credential, web apps can issue an **HTTP session** or short-lived token with proper validation.

| How requests are authenticated | Does password hashing run every request? | Notes |
| --- | --- | --- |
| Form login with session | Usually **no**; verified only at login/re-auth | Session validation, expiry, CSRF, cookies, and revocation must still be protected |
| HTTP Basic on every API request | Possibly **yes**, depending on provider and caching | Calling `UserDetailsService` and `matches` per request is very expensive; use only when appropriate |
| API JWT access token | Usually no password hashing; verified with public key/HMAC | Must verify signature, issuer, audience, expiry, scopes, and resource policies |
| Opaque token introspection | No password hashing at API; usually calls IdP over network | Cost shifts to remote validation/introspection |
| OIDC browser login + app session | Password (if used) handled at IdP; app receives validated result | Callbacks, token endpoint, sessions, and business authorization still require checks |
| Dedicated API key | Differs from password login by default | Requires token/API key validation, secret protection, scopes, and dedicated rate limiting |

**Do not treat short-lived sessions/tokens as "skipping authentication".** Session IDs must be unpredictable and cookie-protected; tokens must be validated properly; resource-level permissions must still be checked. Optimization means reducing **unnecessary long-term credential verification**, never relaxing security constraints.

## 9. Latency when integrating external authentication services

An architecture may connect to:

- LDAP/Active Directory to look up accounts or authenticate credentials.
- An OIDC/OAuth2 IdP for redirect login, authorization code exchange, or user info retrieval.
- An OAuth2 introspection endpoint to verify opaque tokens.
- A JWKS endpoint to fetch public keys for JWT validation.
- A UserInfo endpoint or group/membership mapping service.
- MFA, fraud/risk assessment, device posture, or directory-sync services.

Each introduces different latency profiles. Never lump everything into one `login.duration` metric and optimize blindly.

| Integration | When called? | Main latency source | Impact if IdP fails |
| --- | --- | --- | --- |
| OIDC interactive login | Starting/completing login or re-auth | Browser redirects, user time, token exchange, key/claim checks | New logins may fail; existing sessions depend on policy |
| LDAP bind/search | During LDAP auth or lookup | Network, TLS, directory search, server load | Cannot auth/look up accounts without an approved fallback |
| JWT resource server | Every request: crypto verify/claims; key fetch when needed | Verify CPU is tiny vs. password hash; JWKS cache miss hits network | Requests needing uncached keys may fail; cached valid keys may continue |
| Opaque-token introspection | Typically every Bearer request needing validation | Remote network/IdP latency on the request path | API cannot verify tokens; must fail closed |
| UserInfo/profile/group lookup | When app genuinely needs external attributes | Remote I/O, rate limits, cache staleness | May affect login or authorization per policy |
| Token refresh | When access token expires/needs renewal | Remote token endpoint | Cannot refresh tokens; refresh tokens must remain protected |

**JWT is not "free".** Cryptographic verification and JSON parsing still consume CPU, especially at high scale. Still, it typically avoids a per-request round-trip to the IdP once needed public keys are cached. Always evaluate audience, algorithm, issuer validation, and key rotation alongside performance.

## 10. Spring Security Resource Server: JWT and opaque introspection

In a Spring Boot 3.x / Security 6.x Servlet API, add `spring-boot-starter-oauth2-resource-server` to configure Bearer tokens. Never build a custom JWT "verifier" that Base64-decodes the payload while ignoring the signature.

### 10.1. Locally verified JWT access tokens

`src/main/resources/application-jwt.properties`—replace the URL with your real trusted issuer:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.test/realms/demo
```

An API Spring Security chain can configure:

```java
// Snippet inside an API @Configuration class.
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
```

This is a **configuration snippet**, not a complete Spring Boot program. It requires imports for `Bean`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`, and the OAuth2 Resource Server starter.

Per Spring Security 6.5 docs, configuring `issuer-uri` may defer metadata and JWKS discovery **until the first JWT request** in matching setups; do not assume every version calls the IdP at startup. Once valid keys are cached, subsequent requests verify JWTs locally. When keys rotate, the system must fetch updated JWKS and handle refresh/caching properly.

To declare the JWKS URI explicitly while retaining issuer validation, provide **both** properties:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.test/realms/demo
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://idp.example.test/realms/demo/protocol/openid-connect/certs
```

Per Spring Security 6.5 mechanics, setting `jwk-set-uri` prevents the resource server from calling the IdP discovery endpoint at startup, while `issuer-uri` still validates the `iss` claim. **The JWKS path above is an example from one IdP type**; obtain the real URI from your provider's metadata/docs.

Do not let JWKS caching bypass expired tokens, wrong issuers, missing scopes/authorities, or mismatched audiences. **Configuring `issuer-uri` does not automatically guarantee `aud` matches your API**; add an `aud` validator and test your token contract. Test key cache TTL and rotation too: a new key during IdP rotation can spike p99 due to key misses/fetches rather than password-hashing CPU.

### 10.2. Opaque-token introspection performs remote calls

When an API accepts opaque Bearer tokens, a Spring Boot 3.x config looks like:

```properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://idp.example.test/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=${INTROSPECTION_CLIENT_ID}
spring.security.oauth2.resourceserver.opaquetoken.client-secret=${INTROSPECTION_CLIENT_SECRET}
```

`${...}` resolves via Spring Boot environment variables when copied; never commit real client secrets to Git. With the OAuth2 Resource Server starter and matching config, Spring Security calls the introspection endpoint to check whether the token is active and retrieve scopes/authorities; **this introduces network latency directly onto the request path**.

Distinguish clearly:

- A token returning `active=false` from the IdP is **invalid**: reject per authentication failure.
- Introspection failing due to network timeout/503 means **unverifiable**: **never treat the token as valid**. Never fall back to `permitAll()`, skip validation, or trust a caller-supplied user ID header.
- A valid token lacking resource permissions is still rejected during authorization even when introspection succeeds.
- Introspection is the policy source of truth for token state; if you cache `active` results, you accept the corresponding revocation lag. Make that decision explicitly with a risk assessment.

Retry introspection cautiously: retrying every error immediately multiplies traffic and can topple an already overloaded IdP. Retry only carefully chosen transient errors when time budgets and request idempotency permit, using backoff/jitter, total retry caps, circuit breakers, and concurrency caps.

### 10.3. Comparing JWT and introspection accurately

| Criterion | Local JWT validation | Opaque introspection |
| --- | --- | --- |
| Must API requests call the IdP? | Not on every request once valid keys are cached | Typically a remote call per token-bearing request |
| Typical latency | Crypto verify/parse/claim checks + occasional JWKS miss | Network/TLS + IdP processing + queues |
| IdP downtime | Cached keys can keep verifying already-issued tokens if policy permits | May be unable to verify tokens, causing rejections/failures |
| Near-real-time revocation | Needs short TTLs, denylists, or additional checks | Can reflect current token state via introspection |
| Throughput scaling | Bound by API CPU and public-key distribution | Bound by IdP throughput/quotas and client connection pools |
| Cache risks | Stale/rotated keys, stale claims for token TTL | Caching active tokens extends the revocation window |
| Common policy | Check signature, `exp`/`nbf`, `iss`, `aud`, scopes, tenant | Check active response, client auth, scopes, resource authorization |

Do not pick JWT **just because it's fast** if the product demands immediate revocation or complex access policies; nor pick introspection **just because it's easy** if the IdP cannot meet API throughput and latency needs. The choice belongs to security architecture and operational requirements.

## 11. Timeouts, retries, circuit breakers, and connection pools

### 11.1. Budgeting time from the outside request inward

Suppose an API has a 500 ms p95 SLO. Calling three sequential dependencies each with a 2-second timeout **blows the request budget immediately during any outage**. Budget downward from the end-to-end target.

```text
User/API request budget = T_total

T_total must cover:
  routing + TLS/proxy + auth validation
  + business processing + data store
  + response serialization + network

Illustrative example (not a universal config):
  Total API deadline 1000 ms
  auth dependency budget max 300 ms
  DB/business/response use the remainder + headroom

If the IdP misses the deadline, never extend
requests indefinitely and never skip authentication.
```

**Do not apply the same deadline to interactive user OIDC logins.** Users take time to complete MFA; authorization requests/sessions at the IdP follow protocol-specific timeouts. Connect/read/response timeouts belong on backend HTTP client-to-IdP calls such as token exchange and introspection.

### 11.2. Distinguishing timeouts at each layer

- **Connect timeout:** failed to establish a TCP connection to the endpoint.
- **TLS handshake timeout:** TCP connected, but TLS failed to finish.
- **Response/read timeout:** request sent, but full response did not arrive in time.
- **Connection pool acquisition timeout:** waiting for a free connection because the pool is full.
- **Overall deadline:** maximum total time for the entire auth step, including queuing, connect, retries, response, and processing.

Do not set only a 5-second read timeout while ignoring queues/pools; a request can wait far longer before reading even starts. Track which timeout fires and whether retries amplify traffic to the IdP.

### 11.3. Retries do not always improve availability

Suppose 100 requests/s hit introspection; if all retry 3 times on IdP 503s, the IdP receives **400 requests/s** right when it is struggling. Cap retries, use jittered backoff, and shed load when upstream fails. Never retry 401/invalid-token responses hoping a token becomes valid; those are authentication outcomes, not transient network failures.

A circuit breaker can stop calling an unhealthy IdP to protect resources. However, **an open circuit must never grant access to requests**. Fail closed by rejecting requests or marking the auth dependency unavailable per policy; the API may return 503 when upstream failure is distinguished, though exact status codes depend on exception handlers and framework setup. Never claim Spring Security always returns 503 by default on introspection timeouts.

### 11.4. HTTPS connections to the IdP

Do not open a brand-new TLS handshake for every introspection call if the HTTP client and infrastructure support safe connection pooling. Connection reuse cuts network overhead; it **does not** relax token verification or allow skipping TLS certificates. Configure max connections, pending acquisitions, connection lifetimes, DNS TTLs, and strict TLS validation per policy. A custom client missing a truststore or disabling hostname verification is a severe vulnerability.

## 12. Caching cuts latency, but trust duration must be governed

The word "cache" carries very different implications depending on what is cached:

| Cache | Potential benefit | Security warning |
| --- | --- | --- |
| JWKS public keys | Cuts network calls; enables local JWT verification | Must refresh on key rotation, bound TTL, and reject untrusted keys |
| OIDC discovery metadata | Cuts issuer/endpoint lookups | Handle config/key changes cleanly |
| Directory profile/groups | Cuts remote LDAP/UserInfo calls | Roles/memberships can be revoked; enforce TTL/invalidation |
| Token introspection result | Cuts remote validation calls | Caching `active=true` extends how long revoked tokens remain usable |
| HTTP session | Avoids per-request password hashing; keeps login state | Protect session IDs, cookies, expiry, fixation, and revocation |
| User details | Cuts user DB queries | Account disable/lock/role changes must propagate within SLA |
| Password verification result | Could skip repeated hashing | **Never casually cache "raw password valid"**—creates credential-equivalent storage risks; prefer properly designed sessions/tokens |

**Never cache raw Bearer tokens in logs, URLs, metric labels, or plaintext databases** for speed. If introspection results must be cached, design protected keys (e.g., keyed derivation/HMAC instead of raw tokens in keys/logs), cap TTL within `exp`/revocation policy, bound size, and lock down cache access. Both tokens and "active" flags can be sensitive.

### JWKS key caching and rotation

A new key from the issuer carries a `kid` absent from the cache. Fetching JWKS can spike latency or time out under load or during an IdP outage. Track cache misses/refreshes/failures and test key-rotation scenarios upfront. Never allow arbitrary signing algorithms taken from untrusted token headers; accept only explicitly configured trusted algorithms.

### Caching policy decisions and privileges

Suppose a user holds a valid JWT whose ADMIN privilege was just revoked. If the app trusts stale role claims in the token for its entire lifetime, **privilege revocation latency** equals the token TTL. This is not merely a performance issue; clarify business requirements for near-real-time revocation and add appropriate account/tenant status checks.

## 13. WebFlux apps: never hash passwords on the event loop

In WebFlux, the Netty event loop serves many concurrent connections. `PasswordEncoder.matches` is CPU-bound and synchronous; running it inside reactive callbacks on the event loop increases latency for **every request sharing that event loop**.

Illustrative **reactive service method snippet**, assuming encoder and scheduler are injected/configured:

```java
public Mono<Boolean> verifyPassword(
        String rawPassword, String storedHash) {

    return Mono.fromCallable(
            () -> passwordEncoder.matches(
                rawPassword, storedHash
            )
        )
        .subscribeOn(passwordHashScheduler);
}
```

A bounded `Scheduler` bean (illustrative, **not a universal default for every machine**) could look like:

```java
@Bean(destroyMethod = "dispose")
Scheduler passwordHashScheduler() {
    return Schedulers.newBoundedElastic(
        4,    // maximum threads in the demo
        100,  // maximum queued tasks per scheduler
        "password-hash"
    );
}
```

These snippets belong in a project with Reactor, Spring Beans, and imports for `Mono`, `Scheduler`, and `Schedulers`; **they are not a standalone compilable program**. Offloading to a scheduler keeps the event loop unblocked, **but does not make hashing cheap on CPU**. Four threads can still be too many if Argon2 consumes heavy RAM; 100 queued tasks can create large tail latency. Measure and size threads/queues from your CPU/memory budget and arrival rate rather than copying demo constants.

If using a custom reactive Spring Security authentication provider, verify how it executes; **never wrap a blocking password encoder in a `Mono` labeled "reactive" while still running on the event loop**. In Servlet/MVC apps, hashing still consumes CPU despite the thread-per-request model; adding Tomcat threads does not add CPU cores.

## 14. Real-world observability with metrics and tracing

### 14.1. Separating metrics by stage

Key signals to measure:

| Metric / group | Meaning |
| --- | --- |
| `auth_password_verify_duration_seconds` | p50/p95/p99 hash verification per instance/algorithm |
| `auth_login_total{outcome}` | Login success/failure/rate-limited rates without usernames |
| `auth_queue_depth` / `auth_queue_wait_seconds` | Backpressure and queued hashing tasks |
| CPU throttling, usage, load | CPU-bound hashing or container quota throttling |
| Heap/non-heap/RSS, GC | Memory pressure, especially with memory-hard hashing under concurrency |
| `auth_external_call_duration_seconds{operation,provider}` | Latency of LDAP/token/introspection/UserInfo/JWKS calls |
| External timeout/5xx/429 counts | Distinguishes provider failures from caller errors |
| Connection pool utilization / pending | Pool exhaustion or acquisition queuing |
| JWT JWKS cache hit/miss/refresh | Spikes during key rotation |
| Session/token issuance, refresh failures | Impact on login and renewal UX |
| End-to-end / browser login timing | Separates user MFA wait from backend HTTP calls |

These metric names are **examples for your own observability setup**; Spring Boot does not automatically emit all of them simply by enabling `Actuator`. With Micrometer/Observability, choose low-cardinality names, units, and tags following organizational conventions.

**Never put usernames, emails, raw client IPs, access tokens, session IDs, or raw exception messages into metric labels.** Use bounded operation names (`password_verify`/`introspect`/`jwks_fetch`), normalized outcomes (`success`/`invalid`/`timeout`/`dependency_error`), and predefined provider names.

### 14.2. Measuring at the right boundary without accidentally including network

Wrapping a timer around the `POST /login` controller includes request parsing, DB queries, password matching, session creation, and response writing. To see whether the **work factor** slows logins down, place a dedicated timer around `PasswordEncoder.matches` inside the authentication provider or helper (never logging raw passwords). Likewise, to separate network waits from IdP processing, time remote calls and observe connect/pool-acquisition/TLS/response phases where supported.

Illustrative Java snippet given a `MeterRegistry registry` and `PasswordEncoder encoder`:

```java
boolean verifyAndMeasure(
        String rawPassword,
        String storedHash,
        MeterRegistry registry,
        PasswordEncoder encoder) {

    Timer.Sample sample = Timer.start(registry);
    boolean ok = false;

    try {
        ok = encoder.matches(rawPassword, storedHash);
        return ok;
    } finally {
        sample.stop(
            registry.timer(
                "auth.password.verify",
                "outcome", ok ? "matched" : "not_matched"
            )
        );
    }
}
```

This is a **method snippet** requiring Micrometer, `MeterRegistry`, and `Timer`; not a standalone class. It uses only a bounded outcome label and records no passwords/hashes. On exceptions (e.g., malformed hash format), `not_matched` in this snippet lumps errors with wrong passwords; production should distinguish `error` for accurate telemetry. More importantly, exceptions **must be handled/propagated** per auth policy and never turned into "login success".

### 14.3. Tracking p95/p99, not just averages

When a dependency stalls sporadically, p50 can look healthy while p99 spikes and causes waves of login failures. Measure p95/p99 over adequate sample windows, separating fresh logins, cache hits/misses, and providers. A 12-sample p99 in a lab exercise has no statistical significance; run load tests long enough with realistic distributions.

Traces show a request traversing account lookup, password verification, token exchange, and business authorization, **but never place access tokens, passwords, ID tokens, Cookies, or PII bodies into spans or baggage**. Manage request IDs and sampling strategies to avoid leaking identities.

## 15. Designing performance and reliability tests

A useful load-test plan separates **algorithm benchmarking** from **system load testing**.

### 15.1. Testing password hashing in isolation

- Run benchmarks on instances/containers with production-equivalent CPU quotas and RAM.
- Warm up the JVM/JIT adequately with sufficient samples; measure both `encode` and `matches` across multiple strengths/work factors.
- Measure a single request on an idle machine for a baseline.
- Measure concurrency 2, 4, 8, ... within allowed bounds; observe saturation instead of assuming more threads are always better.
- For Argon2/scrypt, measure RSS/heap pressure and memory-exhaustion risk.
- Test both right and wrong passwords; real auth logic may differ on non-existent usernames.
- Conclude with a work factor aligned to security goals, throughput, SLOs, and operational headroom.

### 15.2. Testing local login APIs

Use **dedicated test accounts** and valid requests with explicit RPS caps in an authorized staging environment. Verify:

| Scenario | Goal |
| --- | --- |
| Single valid user login | End-to-end and verification baseline |
| Wrong password | Errors reveal no account info and cause no abnormal overload |
| Non-existent user | Minimize unnecessary timing differences; prevent enumeration |
| Short burst | Rate limiter, bounded queues, and CPU behavior |
| Sustained load | CPU, p95, p99, retries, login error rates |
| Locked/disabled account | No session/token issued for ineligible accounts |
| Password policy upgrade | Load of rehashing new hashes plus legacy hash compatibility |
| Cancel/timeout | No leakage of request contexts, threads, or passwords into logs |

Never run credential-stuffing tests against third-party systems. In exercises, use authorized internal load generators and synthetic accounts—never real passwords or credentials.

### 15.3. Testing dependency latency

Use a **mock IdP or authorized integration environment** to inject faults deliberately:

```text
Case A: Normal IdP response, e.g., 100 ms
Case B: Unusually slow IdP response, e.g., 1500 ms
Case C: TCP connect timeout / TLS handshake failure
Case D: IdP HTTP 503 or 429
Case E: Introspection returns active=false
Case F: JWT has uncached kid / JWKS refresh
Case G: IdP rotates keys and resource server fetches new key
Case H: IdP unreachable while web users hold valid sessions
```

Durations and statuses above are **synthetic test inputs**, not any real provider's latency. Verify the application:

- Never lets unverifiable tokens pass.
- Never retries infinitely or creates unbounded connection/task queues.
- Distinguishes invalid credentials from dependency unavailability in logs, metrics, and HTTP responses per policy.
- Keeps p95/p99 and resilience of non-IdP features within designed bounds.
- Ensures existing sessions and tokens with cached keys behave per policy during IdP outages—neither claiming all requests succeed nor assuming all must fail.
- Triggers alerts and has a runbook when external auth becomes a bottleneck.

### 15.4. Validating outcomes with data instead of guesswork

**Illustrative examples, not measured data:**

| Change | Data to inspect | Possible explanation |
| --- | --- | --- |
| Raise bcrypt cost | Verify p50/p95, CPU util, login RPS | Offline safety rises, but required CPU cores also rise |
| Grow bcrypt thread pool | CPU, queue wait, GC, p99 | May not increase throughput once CPU is saturated |
| Reduce Basic password checks | Login frequency, session/token safety, RPS | Cuts hashing load if sessions/tokens are designed properly |
| Switch from introspection to JWT | IdP RPS, JWT validation latency, revocation freshness | Cuts remote validation while changing the revocation model |
| Enable sensible JWKS caching | Cache hits/misses, key rotation, 401 spikes | Cuts network calls while still needing clean refresh |
| Enable introspection caching | IdP RPS, cache TTL, revocation tests | Cuts latency while extending revoked-token usability |
| Set budget-aligned timeouts | Request p99, dependency timeouts/errors | Stops threads hanging; must fail closed |
| Bound concurrency | Queue depth, 429/503, success SLO | Controlled rejections prevent whole-system collapse |

## 16. Common mistakes when optimizing authentication

### 16.1. Lowering bcrypt work factor just to speed up logins

Side effect: offline cracking cost drops. Better steps: benchmark, right-size, improve rate limiting, cut redundant hashes, isolate workers/resources, and review hash policies; if cost must change operationally, obtain risk sign-off and an upgrade roadmap.

### 16.2. Using SHA-256 or NoOpPasswordEncoder to boost throughput

**Unacceptable.** Fast hashes or plaintext are not secure password storage. `DelegatingPasswordEncoder` supports migration, yet never leave a `noop` fallback in production just to "avoid errors."

### 16.3. Blaming bcrypt for every slow request

When users sign in via an IdP, the Spring app may not hash passwords at all; latency may sit in the IdP, MFA, token exchange, JWKS, database account mapping, or browser redirects. Measure each stage instead of blindly tuning the encoder.

### 16.4. Checking user details and hashing passwords on every API GET

APIs presenting long-term credentials on every request hit a throughput ceiling set by hashing cost. Consider securely managed short-lived sessions or tokens—never invent plaintext "userId" cookies.

### 16.5. Running BCrypt directly on the Netty event loop

Blocks the event loop. Offload CPU/synchronous work to a bounded `Scheduler`/`Executor`, recognizing that CPU cost remains and concurrency/queues must be capped.

### 16.6. Caching "this password is valid" results without controls

A password-verification cache becomes credential-equivalent storage, increasing secret-leakage risk, broken revocation, and raw passwords entering cache keys. Prefer proper session/token designs over ad-hoc password-match caches.

### 16.7. Retrying every introspection failure

Amplifies load onto an unhealthy IdP, stretches requests, and builds queues. Retry only recoverable errors within time budgets, never invalid tokens.

### 16.8. Allowing tokens when the IdP fails to respond

That is **fail-open** and breaks the authentication boundary. If a token cannot be verified per policy, never grant access. Configure proper statuses, alerts, and recovery runbooks.

### 16.9. Assuming JWTs never need the network

JWKS and issuer metadata still need fetching and refreshing. A new `kid` can trigger a fetch right during an IdP outage. Test key rotation and outages; never skip signature validation when a key is absent from cache.

### 16.10. Accepting any JWT solely because its signature is valid

You must also check issuer, audience/recipient, expiration, not-before, scopes/authorities, and token type where needed; a valid signature does not grant access to someone else's resources.

### 16.11. Sizing threads mechanically from vCPU count

Password hashing and remote HTTP calls have completely different resource profiles. Thread budgets must match CPU/memory/queues and runtime limits. Container quotas, CPU throttling, and noisy neighbors heavily impact benchmarks too.

### 16.12. Returning 401 for every failure without tracking cause

Invalid credentials/tokens are authentication failures; IdP timeouts are dependency failures. Spring Security/default handlers may map statuses differently, yet metrics and runbooks must identify the source. Never count upstream errors as bad-password attempts that trigger mass account lockouts.

## 17. Investigation runbook for sudden authentication latency spikes

1. **Identify the auth path:** local hash, HTTP Basic, form session, OIDC, JWT, or introspection. Never start by changing the work factor.
2. **Compare cohorts:** fresh logins vs. existing sessions, cache hits vs. misses, public endpoints vs. Bearer endpoints.
3. **Measure symptoms:** p50/p95/p99, RPS, 401/403/429/5xx, timeouts, queue depth, CPU throttling, RAM/GC.
4. **If CPU spikes alongside password verification:** check login bursts, insufficient rate limits, recent hash-cost changes, or high Basic-auth volume.
5. **If CPU is low yet auth is slow:** check DNS/TLS, HTTP client pools, connection reuse, IdP latency, LDAP queries, retries, and timeouts.
6. **If only new JWTs fail:** check JWKS endpoint, cache misses/key rotation, issuer/audience, and clock skew.
7. **If only opaque tokens lag:** measure introspection p95, IdP RPS/429s, active client connections, retry amplification, and policy-approved caching.
8. **If OIDC login lags while regular API calls stay fast:** separate browser redirect/MFA/IdP session waits from backend token exchange and account lookups.
9. **If unexpected 401/403 spikes occur:** never disable validation; inspect token types/expiry/scopes, sessions, and resource/tenant policies.
10. **Post-incident:** re-run negative tests, update alerts and capacity plans, and dial back verbose debug logs containing sensitive context.

### What to record and never record during investigation

**Safe to record:** non-sensitive request IDs, fixed operation codes, allowlisted provider/route names, latencies, status classes, error categories, and cache/queue states. **Never record:** passwords, password hashes in logs, access/refresh/ID tokens, `Authorization` headers, session cookies, MFA codes, raw IdP responses containing PII, or client secrets.

Hashing/encrypting user IDs in logs does not automatically anonymize data; evaluate purpose, read permissions, and audit retention per data policy.

## 18. Deployment checklist for performant and secure authentication

- [ ] Clearly distinguish when passwords must be verified vs. when sessions/tokens suffice.
- [ ] Use reliable adaptive password hashing; never store plaintext or fast hashes.
- [ ] Benchmark the encoder on production-equivalent CPU/RAM/quotas; compare `encode` and `matches`.
- [ ] Tune work factor using security guidance, real SLOs, and headroom—never copy a "standard" number blindly.
- [ ] Size capacity from login RPS, CPU-seconds/verify, memory per verification, and concurrency.
- [ ] Enforce rate limits, bounded executors/queues, credential-stuffing monitoring, and safe operational fallbacks.
- [ ] Never run blocking password hashing on the WebFlux event loop.
- [ ] Distinguish OIDC web login, JWT resource servers, opaque introspection, LDAP, and UserInfo calls.
- [ ] For JWTs: verify signature, issuer, audience, expiry, scopes, and JWK rotation; cache keys per policy.
- [ ] For introspection: configure timeouts, connection pools, retry budgets, circuit breakers, and fail-closed policies.
- [ ] Never cache raw credentials/tokens casually; factor TTL and revocation lag into auth caches.
- [ ] Define separate SLOs for fresh logins, API authentication, and IdP dependencies.
- [ ] Monitor p95/p99, RPS, timeouts, CPU, RAM, queues, cache misses, and IdP 429/5xx.
- [ ] Test invalid credentials/tokens, disabled accounts, JWKS key rotation, IdP outages, and overload.
- [ ] Never log passwords, tokens, cookies, client secrets, or sensitive IdP payloads.
- [ ] After optimizations, re-verify resource authorization, CSRF/sessions, and negative security tests.

**Conclusion:** password hashing **should be intentionally slow** to protect credentials if hashes leak, while remote authentication **must not become unpredictably slow** due to unbounded connections, queues, or retries. Secure systems do not "speed up" by dropping hashes or skipping token checks; they **measure the right stages, avoid redundant long-term credential checks, pick the right session/token model, bound resources, and fail closed on external dependencies**.

### Official documentation and references

- [Spring Security 6.5 — Password Storage, Adaptive Work Factor and DelegatingPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — Servlet OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Servlet OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — Reactive Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
