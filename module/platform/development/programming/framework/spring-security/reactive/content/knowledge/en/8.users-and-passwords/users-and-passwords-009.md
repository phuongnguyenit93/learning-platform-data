# Username Normalization and Preventing Account Enumeration

> **Module:** Spring Security - reactive  
> **Parent Topic:** Users and passwords  
> **Goal:** Build a consistent username key across registration/login/recovery while avoiding leaking whether an account exists via responses, HTTP codes, timing, and side channels. Includes Java 17+, Spring WebFlux/Spring Security, WebTestClient, and security tests.

## 1. Two Problems to Solve Together

Someone registers as `Alice`, logs in with `alice`, and requests password recovery with ` ALICE `. If those three places normalize differently, lookups fail or allow logically duplicate accounts. With Unicode, `ＡＬＩＣＥ` (fullwidth Latin letters) can even look like `Alice`.

An attacker tries `alice`, `admin`, `bob` in turn on the login or forgot-password screen. If the API returns "User not found" for unknown names yet "Wrong password" for real names, they now have an account list for credential stuffing, password spraying, and phishing.

**Username normalization** produces a stable logical identifier. **Preventing account enumeration** avoids disclosing account lookup results to unauthenticated callers. The two techniques belong together, yet solve different problems.

After this lesson, learners should be able to:

1. Propose a clear `username_key` policy, including Unicode and case handling.
2. Explain why storing a separate canonical key and database unique constraint is necessary.
3. Distinguish username normalization from email normalization and password verification.
4. Build a Spring WebFlux login path that keeps failures to **the exact same error type** across nonexistent users, wrong passwords, and disabled accounts.
5. Reduce timing discrepancies via password matching against a dummy hash for nonexistent cases, while understanding why "constant-time" cannot be promised for every HTTP request.
6. Design forgot-password/registration flows that do not become account-discovery oracles, with rate limiting and negative tests.

## 2. User Data: ID, Display Name, Login Key

Do not use a single username string for every purpose.

| Attribute | Meaning | Example |
| --- | --- | --- |
| `user_id` | Immutable internal identifier | UUID |
| `username_display` | Name displayed to users | Alice |
| `username_key` | Normalized key for lookup/uniqueness checks | alice |
| `password_hash` | Salted/work-factor hash; never store raw password | `{bcrypt}...` |
| `status` | Internal status | ACTIVE, DISABLED, LOCKED |
| `verified_email` | Contact channel with proven ownership | Verified address |

**Use `user_id` for foreign keys, ownership, auditing, and data links**, because usernames can change. `username_key` serves login and logical identity checks; `username_display` should never be the database key. When a username changes, `user_id` stays the same.

Illustrative DDL (adjust syntax per database):

~~~sql
CREATE TABLE accounts (
    user_id          UUID PRIMARY KEY,
    username_display VARCHAR(128) NOT NULL,
    username_key     VARCHAR(32) NOT NULL,
    password_hash    VARCHAR(255) NOT NULL,
    enabled          BOOLEAN NOT NULL,
    CONSTRAINT uq_username_key UNIQUE (username_key)
);
~~~

**Database `UNIQUE` is mandatory.** Checking `SELECT ... WHERE username_key=...` before `INSERT` does not prevent race conditions: two concurrent requests can both see "not found" and both `INSERT`. The DB unique constraint is the final safeguard. Also control DB collation/string comparison: if the DB treats two characters as equal while the canonicalizer does not, the unique key can produce unexpected collisions. Never silently rely on collation to replace application normalization.

## 3. Choosing an Explicit Canonicalization Policy

No single policy fits every kind of username. For **self-chosen usernames** in this lab, choose an intentionally ASCII-restricted policy:

1. Accept the raw string and check for null.
2. Normalize Unicode to **NFKC**.
3. Strip leading/trailing whitespace with `strip()`.
4. Convert to lowercase with `toLowerCase(Locale.ROOT)` to avoid JVM locale dependence.
5. Accept the final key only if it matches `[a-z0-9][a-z0-9._-]{2,31}` — 3 to 32 ASCII characters.
6. Use that exact final key for registration, login, recovery, renaming, and repository lookups.

| Input | Result Under Lab Policy | Reason |
| --- | --- | --- |
| `Alice` | `alice` | Lowercase |
| `  ALICE  ` | `alice` | Strip + lowercase |
| `ＡＬＩＣＥ` | `alice` | NFKC fullwidth compatibility |
| `alice` | `alice` | Already canonical |
| `al ice` | Rejected | No whitespace allowed in key |
| `al​ice` with zero-width | Rejected | ASCII regex rejects hidden characters |
| `a` | Rejected | Under 3 characters |
| `tênngười` | Rejected **in this ASCII example** | Supporting Vietnamese requires a different Unicode design |

**NFKC is a policy decision, not a mandatory rule for every product.** It folds some compatibility characters yet does not eliminate all visually confusable cases, such as Cyrillic characters resembling Latin letters. Unicode UTS #39 provides mechanisms for detecting confusables and script restrictions. If supporting international usernames, design policies for character sets, normal forms, scripts, rendering, Unicode versions, and collision handling. The lab's ASCII policy is simple so it can be verified cleanly with tests; never apply it mechanically to systems requiring multilingual names.

**Why `Locale.ROOT`?** Parameterless `toLowerCase()` depends on the machine locale; handling the letter `I` differs in certain locales. Identity keys must be stable across servers/deployments. Also note that Java's lowercase **is not strictly equivalent to Unicode full case folding**; the post-normalization ASCII regex constrains the example's output.

**Idempotency:** `canonicalize(canonicalize(x)) = canonicalize(x)` for every valid `x`. **Collision:** Two distinct raw names mapping to the same key are **one logical identity**; never create two accounts. **Stability:** Changing policy or Unicode versions when users already exist requires collision auditing, alias resolution, and controlled migration.

## 4. Usernames Differ from Emails and Passwords

Emails follow different rules than usernames: the **domain** relates to case-insensitive DNS and IDNA; the **local-part** has complex rules and may depend on the provider. Never blindly lowercase the entire local-part, strip dots, drop `+tag` suffixes, or assume every provider treats emails identically like one popular service does. Email login needs its own policy, ownership verification, and consistent key/email uniqueness definitions.

Passwords are **secrets**, not usernames. **Do not** apply username `strip()`, `toLowerCase(Locale.ROOT)`, or NFKC arbitrarily to passwords: that can alter the secret and reduce entropy. When supporting Unicode passwords, NIST SP 800-63B recommends **consistent NFC** before hashing/verifying; it must be documented and applied identically at registration and login, without silently altering existing users. Passwords must be verified **in full**, never truncated. Check your `PasswordEncoder` choice and algorithm byte limits explicitly.

Separate the three concepts: **username canonicalization** to locate accounts; **email verification** to prove a communication channel; **password hashing** to protect secrets. Do not use a single "normalizeAllStrings" function for all three.

## 5. Account Enumeration: Leakage Channels

Attackers can probe for accounts through these differences:

| Channel | Common Leak | Mitigation |
| --- | --- | --- |
| UI message | "User not found" vs. "Wrong password" | One generic message |
| HTTP status | 404 for unknown user, 401 for wrong password | Same status class for failed auth branches |
| Response body | Different JSON fields, codes, lengths | Consistent schema/body |
| Headers/redirects | Different error login URLs, cookies, challenges | Inspect actual responses across the whole stack |
| Timing | Unknown user returns fast, real user runs bcrypt/Argon2 | Dummy hash verification and controlled scheduling |
| Forgot password | "Email sent" vs. "Address not found" | Conditional message "if an account exists..." |
| Registration | Unbounded public `username_exists=true` check | Evaluate UX, out-of-band verification, rate limits |
| MFA/SSO | Showing MFA step or provider only for real names | Design challenge flow without early disclosure |
| Email/side effects | Only known users trigger sync jobs and slow responses | Process work asynchronously, uniform response |
| Account lockout | Known users show distinct lockout responses | Do not disclose status via public login |

Public error messages should be equivalent across **nonexistent user, wrong password, disabled account, and locked account**, per the OWASP Authentication Cheat Sheet. For form login or APIs, use something like "Invalid username or password". For HTTP Basic, a uniform 401 challenge may be appropriate behavior.

Do not force every HTTP error into 401: malformed requests may be 400; authenticated users lacking resource permission get 403. The goal is **not distinguishing account-existence branches within the same credential verification flow**.

## 6. Timing Attacks and Reducing Discrepancies

The following pseudocode has a timing flaw:

~~~text
account = repository.findByKey(usernameKey)
if account is missing:
    return 401            # No password hash verification
if !passwordEncoder.matches(password, account.passwordHash):
    return 401            # Resource-intensive bcrypt/Argon2 runs
~~~

Even though both return 401, an attacker can measure many samples and infer which names trigger password hashing. Never use a fixed `Thread.sleep(100)` as a "fix": it can block the event loop, introduce new skew, and increase DoS risk.

**Better flow:**

~~~text
canonicalKey = normalize(identifier) or mark invalid
account = lookup(canonicalKey) or empty
selectedHash = account.exists ? realHash : precomputedDummyHash
matches = passwordEncoder.matches(rawPassword, selectedHash)
if account.exists && account.enabled && matches:
    authenticated
else:
    generic BadCredentialsException
~~~

Every branch pays one round of password verification against a hash generated with the same algorithm and work factor in the demo. The dummy hash is generated **once at startup**, never regenerated per request. The disabled branch must also go through hash checking before returning the same generic error.

**Constant-time across full HTTP is not guaranteed.** DB queries, caches, indexes, older hashes' work factors, schedulers, GC, gateways, networks, and username lengths can still shift timing distributions. Dummy verification only narrows one very obvious difference; you still need real measurements, rate limiting, anti-automation, and resource controls. Hashing passwords on the event loop is dangerous in WebFlux; offload to an appropriate scheduler or use a standard authentication manager that handles CPU-bound work.

## 7. Account Lifecycle Must Share One Canonicalizer

~~~mermaid
flowchart TD
    A["Input username"] --> B["Single canonicalization"]
    B --> C{"Valid key?"}
    C -->|"No"| D["Do not store / generic auth failure flow"]
    C -->|"Yes"| E["username_key"]
    E --> F["Registration → DB UNIQUE"]
    E --> G["Login → repository lookup"]
    E --> H["Forgot password → silent lookup"]
    E --> I["Rename → collision check + transaction"]
    F --> J["Immutable user_id"]
    G --> J
    H --> J
    I --> J
~~~

Never let the registration controller lowercase, the auth manager only trim, and password reset search raw input. Registration/renaming must check collisions on the final key; login and reset must not construct a different key. When a username changes, data ownership remains tied to `user_id`. If the system uses SSO and identity linking, IdP keys and display usernames must not be conflated.

## 8. Java 17+ Project to Verify Behavior

The sample uses Spring Boot **3.3.13** and Spring Security 6.x for the WebFlux lab. Spring Boot 3.3 has reached end of OSS support; new production projects should pick a supported version and align APIs accordingly. Runnable with JDK 17+, Maven, and localhost:8080.

The app uses **HTTP Basic solely to demonstrate username/password authentication**. It does not issue JWTs or create login sessions after password submission. Outside localhost, Basic must run over **HTTPS** because Base64 does not encrypt credentials. Real projects need password policies, MFA, rate limits, auditing, and sessions/OAuth2/CSRF per architecture.

Structure:

~~~text
reactive-username-security/
├── pom.xml
└── src/
    ├── main/java/example/auth/
    │   ├── AuthApplication.java
    │   ├── UsernameKey.java
    │   ├── DemoAccountStore.java
    │   ├── CanonicalAuthenticationManager.java
    │   ├── SecurityConfig.java
    │   └── AccountController.java
    └── test/java/example/auth/
        └── AuthenticationPolicyTest.java
~~~

### 8.1. Maven

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-username-security</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Use only `spring-boot-starter-webflux`; do not add `spring-boot-starter-web` in the lab.

### 8.2. Spring Boot Application

`src/main/java/example/auth/AuthApplication.java`:

~~~java
package example.auth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthApplication.class, args);
    }
}
~~~

## 9. Writing UsernameKey Under a Specific Policy

`src/main/java/example/auth/UsernameKey.java`:

~~~java
package example.auth;

import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;

public final class UsernameKey {

    private static final Pattern ALLOWED =
        Pattern.compile("[a-z0-9][a-z0-9._-]{2,31}");

    private UsernameKey() {
    }

    public static String of(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Invalid username");
        }

        String key = Normalizer
            .normalize(raw, Normalizer.Form.NFKC)
            .strip()
            .toLowerCase(Locale.ROOT);

        if (!ALLOWED.matcher(key).matches()) {
            throw new IllegalArgumentException("Invalid username");
        }

        return key;
    }
}
~~~

This function **does not query the DB**; it only computes the logical key. `NFKC` and `Locale.ROOT` collapse certain input variants, and the regex restricts the character set. It rejects zero-width and control characters because the final key falls outside valid ASCII. For login, `IllegalArgumentException` must be turned into a **generic authentication failure**; on a new-username signup form you can state format rules without disclosing which names are taken.

## 10. Non-Blocking Illustrative User Store

`src/main/java/example/auth/DemoAccountStore.java`:

~~~java
package example.auth;

import java.util.Map;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

record DemoAccount(
    String usernameKey,
    String passwordHash,
    boolean enabled
) {}

@Component
public class DemoAccountStore {

    private final Map<String, DemoAccount> byKey;

    public DemoAccountStore(PasswordEncoder encoder) {
        this.byKey = Map.of(
            "alice", new DemoAccount(
                "alice", encoder.encode("DemoPassword123!"), true),
            "bob", new DemoAccount(
                "bob", encoder.encode("BobPassword123!"), false)
        );
    }

    public Mono<DemoAccount> findByKey(String key) {
        return Mono.justOrEmpty(byKey.get(key));
    }
}
~~~

Two test accounts: Alice enabled, Bob disabled. Demo passwords appear in source so **never use them in real products**. The in-memory Map models non-blocking lookup to keep the lab simple. Production uses a reactive DB with a unique key, password hashes, and internal status; if blocking JDBC is used, handle blocking boundaries properly instead of calling it on the event loop.

## 11. ReactiveAuthenticationManager: One Uniform Public Error

`src/main/java/example/auth/CanonicalAuthenticationManager.java`:

~~~java
package example.auth;

import java.util.List;
import java.util.UUID;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Component
public class CanonicalAuthenticationManager
        implements ReactiveAuthenticationManager {

    private record Candidate(DemoAccount account, String hash) {}

    private final DemoAccountStore accounts;
    private final PasswordEncoder encoder;
    private final String dummyHash;

    public CanonicalAuthenticationManager(
            DemoAccountStore accounts,
            PasswordEncoder encoder) {
        this.accounts = accounts;
        this.encoder = encoder;
        this.dummyHash = encoder.encode(UUID.randomUUID().toString());
    }

    @Override
    public Mono<Authentication> authenticate(Authentication request) {
        if (!(request instanceof UsernamePasswordAuthenticationToken)) {
            return Mono.empty();
        }

        String password = request.getCredentials() instanceof String text
            ? text : "";

        Mono<DemoAccount> lookup;
        try {
            lookup = accounts.findByKey(UsernameKey.of(request.getName()));
        } catch (IllegalArgumentException invalidName) {
            lookup = Mono.empty();
        }

        return lookup
            .map(account -> new Candidate(account, account.passwordHash()))
            .switchIfEmpty(Mono.just(new Candidate(null, dummyHash)))
            .flatMap(candidate -> Mono.fromCallable(() -> {
                // Run the same password check for known/unknown.
                boolean validPassword =
                    encoder.matches(password, candidate.hash());

                DemoAccount account = candidate.account();
                if (!validPassword
                        || account == null
                        || !account.enabled()) {
                    throw new BadCredentialsException(
                        "Invalid username or password");
                }

                return (Authentication)
                    UsernamePasswordAuthenticationToken.authenticated(
                        account.usernameKey(),
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_USER"))
                    );
            }).subscribeOn(Schedulers.boundedElastic()));
    }
}
~~~

**Why design it this way?**

- Normalize before lookup. Malformed names and nonexistent names both flow through `dummyHash` instead of returning early.
- The dummy hash is encoded **once** in the constructor using the same algorithm and cost as real hashes in the lab. Encoding a fresh one per request could cause heavy CPU consumption.
- Real and dummy hashes are both checked with `PasswordEncoder.matches(...)`. Disabled accounts are also evaluated **after** the password check, ultimately throwing the same `BadCredentialsException`.
- `subscribeOn(Schedulers.boundedElastic())` avoids running heavy bcrypt directly on the event loop. Benchmark schedulers and cap concurrent logins; in real systems, a standard Spring Security manager may be more suitable depending on the authentication mechanism.
- On success, builds `Authentication` with the canonical principal, `null` credentials, and a demo role. Never returns passwords or logs credentials.
- Dummy hashing reduces timing discrepancy but **does not eliminate** DB/cache/scheduler/transport differences. This illustrates one defense layer, not a complete production authentication solution.

## 12. SecurityWebFilterChain Using the Custom Manager

`src/main/java/example/auth/SecurityConfig.java`:

~~~java
package example.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            CanonicalAuthenticationManager manager) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.authenticationManager(manager))
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }
}
~~~

`BCryptPasswordEncoder(10)` is merely a lab config with moderate cost for running tests. In new systems, OWASP prefers **Argon2id** where suitable; pick algorithm/cost via benchmarks, hash-upgrade mechanisms, and resource limits. BCrypt typically limits effective input to **72 bytes**, so systems using bcrypt must ensure passwords are not silently truncated and enforce an appropriate length policy. NIST requires verifying the full password.

HTTP Basic here feeds username/password into the `ReactiveAuthenticationManager`. `authenticated()` does not grant data permissions on its own; real business endpoints must also check roles, owner/tenant, and resource state. Spring WebFlux uses `SecurityWebFilterChain` and `ServerHttpSecurity`, not Servlet MVC's `HttpSecurity`.

## 13. Private Endpoint and Canonical Principal

`src/main/java/example/auth/AccountController.java`:

~~~java
package example.auth;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class AccountController {

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> Map.of(
                "username", ctx.getAuthentication().getName()
            ));
    }
}
~~~

When sending username `ALICE` with the right password, the manager resolves `alice` and the controller returns JSON:

~~~json
{"username":"alice"}
~~~

This is the example's internal key, **not a display name**. Real apps should use `user_id` as the stable subject for all data authorization.

## 14. WebTestClient Tests: Uniform Branches

`src/test/java/example/auth/AuthenticationPolicyTest.java`:

~~~java
package example.auth;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AuthenticationPolicyTest {

    @Autowired
    WebTestClient client;

    @Test
    void keyNormalizesCaseWidthAndWhitespace() {
        assertEquals("alice", UsernameKey.of("Alice"));
        assertEquals("alice", UsernameKey.of("  ＡＬＩＣＥ  "));
        assertEquals("alice", UsernameKey.of("alice"));
        assertEquals("alice", UsernameKey.of(UsernameKey.of("Alice")));
    }

    @Test
    void invalidAndInvisibleUsernamesAreRejected() {
        assertThrows(IllegalArgumentException.class,
            () -> UsernameKey.of("al\u200Bice"));
        assertThrows(IllegalArgumentException.class,
            () -> UsernameKey.of("al ice"));
        assertThrows(IllegalArgumentException.class,
            () -> UsernameKey.of("a"));
    }

    @Test
    void uppercaseAsciiUsernameLogsIntoCanonicalAccount() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("ALICE", "DemoPassword123!"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("alice");
    }

    @Test
    void anonymousIsRejected() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    private EntityExchangeResult<byte[]> rejected(
            String username, String password) {
        return client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(username, password))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody()
            .returnResult();
    }

    @Test
    void unknownWrongPasswordAndDisabledHaveEquivalentResponses() {
        EntityExchangeResult<byte[]> unknown =
            rejected("nobody", "wrong-pass");
        EntityExchangeResult<byte[]> wrong =
            rejected("alice", "wrong-pass");
        EntityExchangeResult<byte[]> disabled =
            rejected("bob", "BobPassword123!");

        // All three already verified status 401 in the rejected helper.
        assertArrayEquals(unknown.getResponseBody(),
                          wrong.getResponseBody());
        assertArrayEquals(unknown.getResponseBody(),
                          disabled.getResponseBody());

        String challenge = unknown.getResponseHeaders()
            .getFirst(HttpHeaders.WWW_AUTHENTICATE);
        assertEquals(challenge, wrong.getResponseHeaders()
            .getFirst(HttpHeaders.WWW_AUTHENTICATE));
        assertEquals(challenge, disabled.getResponseHeaders()
            .getFirst(HttpHeaders.WWW_AUTHENTICATE));
    }

    @Test
    void invalidUsernameAtLoginStillUsesGeneric401() {
        rejected("a", "wrong-pass");
    }
}
~~~

The tests verify idempotent canonicalization, NFKC, blocking zero-width characters, HTTP Basic login with uppercase ASCII, and **identical 401 status/body/challenge** across unknown, wrong password, and disabled cases. If production uses JSON/form login or an API Gateway, verify response schemas, redirects, cookies, error pages, and cache headers on the **real stack**.

**Unicode note for HTTP Basic:** `setBasicAuth` APIs have their own charset rules; do not assume passing fullwidth usernames over Basic is always compatible. NFKC is tested directly on `UsernameKey`, while HTTP tests use ASCII `ALICE`. If Unicode usernames over HTTP are required, choose a supported protocol/charset, test end-to-end, and consider JSON forms.

## 15. Running and Interpreting Results

In the directory containing `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Send requests (`curl -u username` prompts for the password, avoiding saving passwords in command history):

~~~bash
curl -i http://localhost:8080/api/me
curl -i -u ALICE http://localhost:8080/api/me
curl -i -u nobody http://localhost:8080/api/me
curl -i -u alice http://localhost:8080/api/me
curl -i -u bob http://localhost:8080/api/me
~~~

| Username | User-Entered Password | Expectation |
| --- | --- | --- |
| No Authorization sent | None | **401 Unauthorized** |
| ALICE | `DemoPassword123!` | **200 OK**, body `{"username":"alice"}` |
| nobody | Any wrong password | **401 Unauthorized** |
| alice | A wrong password | **401 Unauthorized** |
| bob | `BobPassword123!` | **401 Unauthorized** because disabled, status not disclosed |
| a | Any password | **401 Unauthorized**, format error does not disclose account branch |

Do not assume a 401's default body always matches one specific JSON payload. HTTP Basic usually sends a challenge via `WWW-Authenticate`; tests assert the server's actual output.

## 16. Forgot Password: Generic Responses and Out-of-Band Work

A forgot-password endpoint must never tell an unauthenticated caller "email not registered". Return the same message, such as:

> If the details match an account, recovery instructions will be sent to the verified contact channel.

For the reset flow:

1. Accept username/email and normalize with the **policy matching that identifier type**.
2. Return consistent public status/body for known and unknown accounts. Never return a masked email or username before proving ownership.
3. Enqueue requests into an anti-spam queue with a fast response; the background worker looks up the account and sends only when eligible. Avoid letting "synchronous mail sending" noticeably shift HTTP response times.
4. Reset tokens must be generated cryptographically randomly, strong, short-lived, and single-use; store per security policy and send only to a **verified channel**.
5. Never lock an account or change its password merely because someone submitted a reset request; require valid token/challenge verification before modifying the account.
6. Protect the endpoint from spam and abuse with multi-dimensional rate limits/quotas; never log reset tokens or send them to referrers or analytics.

Illustrative pseudocode, **not a standalone Java program**:

~~~text
POST /forgot-password { identifier }
    → check shape and canonicalize
    → accept request with rate limiting
    → return generic response for known/unknown

background worker:
    → look up account
    → if eligible: generate single-use expiring token
    → send to verified channel
    → audit outcome internally
~~~

Avoid assuming a generic message alone equalizes timing. DB lookups, queues, mail providers, caches, and rate limiting can also expose differences if executed synchronously on the response path.

## 17. Registration: UNIQUE Keys and UX Trade-Offs

Registration must compute `username_key` first, then `INSERT` under the unique constraint. If two people concurrently submit `Alice` and `ＡＬＩＣＥ`, both map to `alice` and the DB allows only one user. A `SELECT` followed by `INSERT` is not enough to stop races under concurrent requests.

For public username-availability checks, showing whether a username is taken helps users pick a name, **while also** giving attackers an account-discovery oracle. Depending on your threat model, use out-of-band email verification, strict rate limiting, CAPTCHA on abuse signals, or accept a controlled disclosure level. Never claim you can completely hide account existence inside a workflow forced to show which names are available.

When changing a canonicalization policy on a legacy system, **audit collisions and run a migration**. Never merge accounts or reassign data ownership when two distinct usernames suddenly map to the same key under a new algorithm. Using an immutable `user_id` preserves data relationships.

## 18. Rate Limiting, Account Lockout, and Brute-Force Defense

A dummy bcrypt hash still consumes CPU; attackers can overload a service by sending floods of invalid requests. Production systems need:

- Rate limits by **IP/subnet, device/session, tenant, pseudonymized canonical identifier**, and total server resources, rather than locking solely by username.
- Detection of password spraying (one password across many users), credential stuffing (many user/pass pairs), and single-account brute force.
- Progressive throttling and CAPTCHA/challenges where appropriate; never let challenge response rules accidentally disclose real accounts.
- Avoid instant account lockouts triggered merely by repeated username attempts, which can cause **denial-of-service** for legitimate users.
- Bound input/request-body lengths, concurrent hash verifications, CPU/schedulers, and queues; pick hash costs suited to system capacity.
- Quiet auditing with correlation IDs and abuse signals; never log raw passwords, Authorization headers, reset tokens, or unnecessary personal identifiers. Unkeyed hashes of emails/usernames in logs are vulnerable to dictionary attacks; use keyed pseudonyms with strict access control and retention.
- Appropriate post-authentication MFA/step-up per policy, avoiding displaying account/MFA setup before the caller proves sufficient eligibility.

Generic errors and dummy hashes **do not replace rate limiting**. An anti-abuse 429 response must not become a signal revealing only real users; test with throttling enabled too.

## 19. Testing Timing and Response Surface

Never write an assertion like `responseTime<100ms` to prove anti-enumeration. In a valid staging environment using test data without probing external accounts:

1. Warm up JVM/JIT, connection pools, password encoders, and caches.
2. Build sets of known/unknown usernames with similar lengths and shapes; send **wrong** passwords for both, plus disabled accounts.
3. Send requests in randomized order and collect enough samples across varying load levels.
4. Compare latency distributions (median, p95, p99), response statuses, body bytes, headers, redirects, cookies, and gateway behavior.
5. Check legacy/modern hashes with differing work factors, cache hits/misses, rate limits, locked users, login/reset/register, and mail queues.
6. If significant discrepancies appear, investigate each layer rather than adding a fixed sleep and declaring it safe.

Absolute "constant-time HTTP" does not exist due to networks and scheduling. Evaluate statistical risk, exploitability at real scale, and integrated defense layers.

## 20. Common Real-World Mistakes

1. **Normalizing only at login:** signup stores `Alice` while login searches `alice` → lookup failures or duplicates.
2. **Missing `Locale.ROOT`:** case conversion varies with server locale.
3. **Trusting NFKC to block all confusables:** different scripts still have lookalike characters; use a proper Unicode policy.
4. **Using username rules for emails/passwords:** can accidentally merge mailboxes or reduce secret entropy.
5. **Checking duplicates with `SELECT` without `UNIQUE`:** race conditions create logically duplicate accounts.
6. **Showing "user does not exist":** leaks account lists.
7. **Same body but differing status/headers:** still an oracle.
8. **Early return for unknown users:** real users run bcrypt, creating a timing signal.
9. **Generating a new dummy hash on every request:** can cause CPU DoS.
10. **Calling bcrypt directly on the event loop:** raises latency for other requests in WebFlux.
11. **Calling `Thread.sleep()` to equalize timing:** blocking and still fails to equalize responses.
12. **Forgot-password returning masked name/email after lookup:** can still leak accounts.
13. **Locking users automatically on reset requests:** attackers easily cause disruption.
14. **Changing canonicalization policy on live data without checking collisions:** two distinct accounts can collide onto one key.
15. **Logging credentials and full emails/usernames:** creates exposure risks and aids attackers.
16. **Testing only successful logins:** fails to prove anti-enumeration.

## 21. Practice Exercises

**Exercise A — canonicalization table:** invent 12 names covering mixed case, fullwidth, whitespace, zero-width, Vietnamese diacritics, and too-short/too-long names. Verify `UsernameKey` output or error and idempotency.

**Exercise B — account uniqueness:** design a database with `UNIQUE` on `username_key`. Send two concurrent registrations for `Alice` and `ＡＬＩＣＥ` and prove only one record is saved. Explain why a `SELECT` pre-check does not guarantee uniqueness.

**Exercise C — uniform error surface:** run unknown/wrong-password/disabled requests via WebTestClient and compare 401, body, and challenge. In the lab, temporarily change one branch to 404 to watch the test catch it, then restore it.

**Exercise D — timing:** temporarily remove dummy hash verification in a copy of the lab environment, measure known/unknown timing distributions, and explain the difference. Restore dummy verification and rate limits.

**Exercise E — password reset:** design a sequence returning a generic message, processing email out-of-band, using single-use tokens, quiet auditing, and spam protection. Write tests ensuring existing and nonexistent accounts do not diverge in responses.

**Exercise F — multilingual Unicode:** if supporting Vietnamese usernames, how would you replace the ASCII policy? Outline normalization, script restrictions/UTS #39, confusable tests, migration, and collision handling.

### Completion Checklist

- [ ] Distinguish `user_id`, `username_display`, and `username_key`.
- [ ] Pick a canonicalization policy and apply it uniformly across every flow.
- [ ] Understand NFKC, `Locale.ROOT`, and Unicode confusables; never apply username rules to emails/passwords.
- [ ] Database `UNIQUE` constraint protects against races/collisions.
- [ ] Unknown users, wrong passwords, and disabled/locked accounts return equivalent public login messages.
- [ ] Both known and unknown accounts go through matching password-hash verification.
- [ ] Do not treat dummy hashing as absolute constant-time; enforce rate limiting and timing tests.
- [ ] `PasswordEncoder` uses proper algorithm/cost; never blocks the event loop.
- [ ] Forgot password, user invites, and registration do not leak accounts via unintended responses.
- [ ] Negative tests and controls over logs/credentials/rate limiting are in place.

## 22. Self-Check Questions

1. Why are `username_display`, `username_key`, and `user_id` all needed?
2. When `Alice` and `ＡＬＩＣＥ` produce the same key, should two accounts be allowed?
3. Does NFKC solve all Unicode spoofing?
4. Why might the lab's ASCII username rule not fit multilingual products?
5. Why can't email local-parts be arbitrarily lowercased or stripped of dots?
6. Is a generic error message alone enough to prevent enumeration? Name three other channels.
7. Why can returning 401 quickly for unknown users still leak accounts?
8. Why should the dummy hash be created once, then passed to `matches` on the unknown branch?
9. When a disabled user enters the right password, how should the public response behave?
10. In WebFlux, why shouldn't CPU-bound password hashing run on the event loop?
11. Should forgot-password change account status before the user proves the reset token?
12. When changing canonicalization policies on an existing database, what collisions must be resolved?

## 23. Official Reference Documentation

- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic messages, discrepancy factors, account enumeration, and anti-automation.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): consistent responses, single-use reset tokens, out-of-band email.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): Argon2id/bcrypt/PBKDF2, hashing/cost, and input limits.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): WebFlux chain, HTTP Basic, reactive security configuration.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder`, `DelegatingPasswordEncoder`.
- [Spring Security — ReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html): Reactive authentication interface.
- [Unicode — UAX #15](https://www.unicode.org/reports/tr15/): normalization forms, NFKC/NFC.
- [Unicode — UTS #39](https://www.unicode.org/reports/tr39/): identifier confusables and script restrictions.
- [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html): password verifiers, Unicode, and full-secret verification.

**Core message:** A login system must compute **one stable canonical username key**, enforce **`UNIQUE` at the database**, and authenticate without publicly disclosing whether an account exists. In Spring WebFlux, collapse failure branches into one uniform outcome, avoid fast exits with dummy password verification, keep hashing off the event loop, enforce rate limits, and test both responses and timing differences.