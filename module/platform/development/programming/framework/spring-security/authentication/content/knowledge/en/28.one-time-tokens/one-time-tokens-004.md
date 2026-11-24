# OneTimeTokenService: Generating, Storing, and Consuming One-Time Tokens in Spring Security

## 1. Objectives and Scope

A **One-Time Token (OTT)** in Spring Security is a secret value issued for an authentication purpose, bound to a user identity and an expiration time; after its first valid use, that value cannot be used to authenticate a second time. A typical case is a **magic link** sent via email: the user requests a login link, opens the email, and submits the token from the link to the application.

The focus of this lesson is the **`OneTimeTokenService`** interface and the complete lifecycle **generate → store → deliver → verify/consume → authenticate**, within the *Spring Security - authentication* module, *One-Time Tokens* group. After this lesson, you should be able to:

1. Call `generate(GenerateOneTimeTokenRequest)` and `consume(OneTimeTokenAuthenticationToken)` properly, understanding the data types and what happens when a token is invalid.
2. Distinguish the responsibilities of `OneTimeTokenService`, `OneTimeTokenGenerationSuccessHandler`, `OneTimeTokenAuthenticationProvider`, and `UserDetailsService`.
3. Choose between `InMemoryOneTimeTokenService` and `JdbcOneTimeTokenService`, knowing the constraints in multi-node deployments and application restarts.
4. Explain why "single use" must be **atomic** when two requests use the same token concurrently.
5. Design tokens with sufficient entropy, short TTLs, protection at rest and in transit, and handling for expired/used/non-existent tokens and email delivery failures.
6. Configure Spring Security Servlet and understand the corresponding Reactive WebFlux version; practice with Java 17+ and test the lifecycle.

**Practice baseline:** Spring Security **6.5.x** (feature available since 6.4), Spring Boot **3.5.x**, Java 17+. For Spring Security 7.x, check the Javadoc for that exact version before reusing code; Servlet and WebFlux examples must not be mixed. This lesson covers OTT for login only, without collapsing every kind of OTP code, password reset, and OAuth token into a single mechanism.

## 2. OTT Is Not TOTP, HOTP, Access Token, or Session

| Type | Where Created / Checked | Usage Rules | Example |
| --- | --- | --- | --- |
| **Spring Security One-Time Token** | Server creates; `OneTimeTokenService` stores and consumes | Used at most once within TTL, typically bound to username | Magic login link |
| **TOTP** | Client authenticator and server both compute from secret + time | Code changes per time window; replay control depends on implementation | Authenticator app |
| **HOTP** | Client/server based on secret + counter | Synchronizes counter, prevents reuse per policy | Counter-based OTP |
| **OAuth access token** | Authorization Server issues; Resource Server validates | Typically reusable multiple times until expiry/revocation | Bearer token for API calls |
| **HTTP session cookie** | Application / session store manages | Identifies an established session; can live across many requests | `JSESSIONID`, `SESSION` |

Spring Security OTT **does not require users to install an OTP app or pre-share a TOTP key**. The server issues the token and must deliver it to the account owner via an appropriate channel such as email. By default, the framework cannot know which email is right, so a dedicated success handler/delivery service must be configured.

An OTT token is only a **short-lived credential to achieve a single login**. After successful authentication, the application typically creates a SecurityContext and login session according to current Spring Security rules. The OTT token does not become the session cookie, and having consumed the token does not mean the newly created session is also single-use.

You must also separate **password reset** and **email verification** purposes: even though both follow a one-time design, they have different audiences/purposes, endpoints, identity verification policies, and consequences. Never reuse a "login" token to automatically change a password, change an email, or activate sensitive privileges.

## 3. OneTimeTokenService API and Related Types

Per the Spring Security 6.5 Javadoc, the interface is located at:

```java
org.springframework.security.authentication.ott.OneTimeTokenService
```

Core contract:

```java
// API shape for explanation; declared in the framework, do not redefine.
public interface OneTimeTokenService {
    OneTimeToken generate(GenerateOneTimeTokenRequest request);
    @Nullable
    OneTimeToken consume(OneTimeTokenAuthenticationToken authenticationToken);
}
```

Key types:

| Type | Role | Data/Characteristics |
| --- | --- | --- |
| `GenerateOneTimeTokenRequest` | Generation request | `getUsername()`, `getExpiresIn()`; constructors `(String)` and `(String, Duration)` |
| `OneTimeToken` | Generated or successfully consumed token | `getTokenValue()`, `getUsername()`, `getExpiresAt()` |
| `DefaultOneTimeToken` | Common implementation of `OneTimeToken` | Constructor `(String token, String username, Instant expireAt)` |
| `OneTimeTokenAuthenticationToken` | Authentication request carrying the token value | `unauthenticated(String)` or `new OneTimeTokenAuthenticationToken(String)`; `getTokenValue()` |
| `OneTimeTokenService` | Generate, store, and consume | `generate(...)` returns a non-null token; `consume(...)` returns the token or null |
| `OneTimeTokenAuthenticationProvider` | Sign in using a token | Calls the service to consume, then uses `UserDetailsService` to load user/authorities |
| `OneTimeTokenGenerationSuccessHandler` | Deliver the token after generation | Sends email/SMS per application logic; **does not authenticate the user** |

**Exact parameter type for `consume`:** In Spring Security 6.5, it takes **`OneTimeTokenAuthenticationToken`**, not `ConsumeOneTimeTokenRequest` and not a raw `String`. This difference easily causes compile errors if you glance at another library's API by mistake.

Example calling the service per contract, a **Java snippet** placed in a class that has `OneTimeTokenService service`:

```java
OneTimeToken issued = service.generate(
        new GenerateOneTimeTokenRequest("alice", Duration.ofMinutes(5)));

String tokenValue = issued.getTokenValue();
Instant expiry = issued.getExpiresAt();

OneTimeTokenAuthenticationToken presented =
        OneTimeTokenAuthenticationToken.unauthenticated(tokenValue);

OneTimeToken consumed = service.consume(presented);

if (consumed == null) {
    // Not found, expired, already used, or invalid.
    // Response must fail closed; do not create a login session.
}
```

The snippet above requires imports from `org.springframework.security.authentication.ott`, `java.time.Duration`, and `java.time.Instant`. It illustrates the service API, **not a controller or standalone runnable program**.

An issued `OneTimeToken` does not mean authenticated; authenticated state happens only after the system verifies the token, maps the right user, and completes the remaining authentication steps.

## 4. End-to-End Flow: Generate, Persist, Deliver, Consume

```text
User/browser                    Spring Security Servlet                    Storage / Mail
     |                                   |                                     |
     | POST /ott/generate                |                                     |
     | username=alice + CSRF             |                                     |
     |---------------------------------->| GenerateOneTimeTokenFilter           |
     |                                   | Resolve GenerateOneTimeTokenRequest   |
     |                                   | OneTimeTokenService.generate(...)     |
     |                                   |------------------------------------->| Save token + expiry
     |                                   |<-------------------------------------|
     |                                   | OneTimeTokenGenerationSuccessHandler |
     |                                   |------------------------------------->| Send magic link
     |<-------- generic confirmation ----|                                     |
     |                                   |                                     |
     |  User opens magic link            |                                     |
     | GET /login/ott?token=...          |                                     |
     |---------------------------------->| Render submit page; fill token form  |
     |  User submits POST /login/ott     |                                     |
     |  + CSRF token                     |                                     |
     |---------------------------------->| OneTimeTokenAuthenticationFilter     |
     |                                   | OneTimeTokenAuthenticationProvider   |
     |                                   | OneTimeTokenService.consume(...)      |
     |                                   |------------------------------------->| Atomically claim/delete if valid
     |                                   |<-------------------------------------|
     |                                   | UserDetailsService -> authorities     |
     |                                   | Establish authenticated session      |
     |<------------ login result -------|                                     |
```

Steps to understand:

1. **Generate**: receives a normalized username/identifier and duration, generates an unpredictable random value, computes expiry, and writes state to storage.
2. **Persist**: stores the minimum data to look up the token, the identity bound to it, expiration time, and consumption state; storage must provide the required consistency.
3. **Deliver**: sends the URL or token to a user-controlled channel. Spring Security does not automatically send emails on the application's behalf.
4. **Submit**: the browser reads the token from the magic link and sends a POST to the login processing endpoint; the browser may pass through an intermediate page before submitting.
5. **Consume**: the service verifies the token exists, is unexpired, and is unused, then **atomically marks it used or deletes it**. Only one request receives valid data.
6. **Authenticate**: the provider looks up the user/authorities using the username bound to the token; account policies such as locked/disabled/expired can still block login.
7. **Session**: after authentication, Spring Security manages SecurityContext, session/cookies, logout, and authorization separately.

**Keep side effects separate:** the email is sent **after** the token is created; do not treat successful sending as the token having been consumed. If delivery fails, the record may remain until expiry/cleanup. If the user opens the email multiple times, only one consume succeeds.

## 5. Secure Token Generation: Entropy, TTL, and Identity

### 5.1. Token Values Must Be Hard to Guess

The goal of a bearer-style magic link token is that outsiders cannot guess it within the TTL. `InMemoryOneTimeTokenService` uses random UUIDs by default; when implementing your own, use `SecureRandom` with at least 128 bits of entropy, commonly 256 bits, encoded as unpadded URL-safe Base64.

Standalone Java 17+ example illustrating **value generation only**, without persisting or issuing sessions. File `TokenValueDemo.java`:

```java
import java.security.SecureRandom;
import java.util.Base64;

public class TokenValueDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    static String newToken() {
        byte[] random = new byte[32];  // 256-bit random secret
        RANDOM.nextBytes(random);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(random);
    }

    public static void main(String[] args) {
        String value = newToken();
        System.out.println("characters=" + value.length());
        // Do not print value to console/log.
    }
}
```

Run:

```bash
javac TokenValueDemo.java
java TokenValueDemo
```

**Exact stdout** (character count, not the random value):

```text
characters=43
```

Do not use `Math.random()`, plain `Random`, incrementing counters, timestamps, or a plain hash of an email address as a login token. The default service's UUID is the framework's internal implementation; the `SecureRandom` example above is intended for **custom storage/services** with specific token format requirements.

### 5.2. Explicit Lifetime

`GenerateOneTimeTokenRequest(String, Duration)` lets you specify the request's TTL. In the default token-generation flow, Spring Security documentation describes a typical TTL of **5 minutes**; an application can customize the request resolver. Do not assume every custom service applies the exact same default TTL without inspecting its implementation.

A token has `expiresAt`: check it using the same trusted time source and the condition **current time is before expiry**. For example, the check is expressed as `now.isBefore(expiresAt)`; at the exact expiry instant, it must be treated as expired. Time zones must be represented via `Instant`/UTC rather than comparing locale date-time strings.

### 5.3. Identity Bound to the Token

`getUsername()` on `OneTimeToken` is the identifier username that the service/provider uses to look up `UserDetails`; it is not proof that the form requester owns the email. In multi-tenant deployments, map and verify the namespace/tenant through a trusted directory, avoiding entering an arbitrary email and letting someone sign into another account with the same username.

Do not accept a user ID from a token-consumption POST parameter to override the stored username. The token itself determines the identity from the record created at issuance. For example, if a consume request carries a valid `tokenValue` for Alice while the body contains `username=bob`, the system must never use Bob.

## 6. Storage: InMemoryOneTimeTokenService

Spring Security Servlet includes the implementation:

```java
import org.springframework.security.authentication.ott.InMemoryOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeTokenService;

OneTimeTokenService service = new InMemoryOneTimeTokenService();
```

Per the Javadoc, this implementation uses a `ConcurrentHashMap` to hold generated tokens and random `UUID`s as token values; expired tokens have a cleanup mechanism triggered when the token count reaches an implementation threshold. `consume` returns the token when valid or `null` when unusable.

**Advantages:** no database required, convenient for testing functionality/reading the API, easy to use for a single instance in demo environments.

**Important limitations:**

- Stored in the memory of **a single process**. On restarts or rolling deployments, unused tokens are lost.
- When running 2+ independent application replicas, a generate request on node A followed by a consume request on node B may fail to find the token. Sticky sessions are not a reliable guarantee for magic links opened from a different browser or device.
- TTL does not mean records are always deleted at the exact moment of expiration; checking expiry during consume and purging records are two separate tasks.
- Do not treat the default memory store as a distributed solution with cross-node transactional guarantees.
- Recovery, auditing, per-user token limits, and reissue policies require additional design.

In a single-node learning app, the default memory service lets you focus on the API flow. When moving to multi-node production or when tokens must survive restarts, choose shared persistence.

## 7. JdbcOneTimeTokenService for Shared Storage

Spring Security Servlet provides `JdbcOneTimeTokenService`, taking a `JdbcOperations` (typically `JdbcTemplate`):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.authentication.ott.JdbcOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeTokenService;

// Snippet inside a @Configuration class:
@Bean
OneTimeTokenService oneTimeTokenService(JdbcOperations jdbc) {
    return new JdbcOneTimeTokenService(jdbc);
}
```

This is a **Spring bean snippet**, requiring an actual `DataSource` and `JdbcOperations` configured by Spring Boot. `JdbcOneTimeTokenService` requires a table matching the schema provided by Spring Security on the classpath:

```text
classpath:org/springframework/security/core/ott/jdbc/one-time-tokens-schema.sql
```

You must create/migrate the schema **before** using the service. Javadoc may give the reference schema resource name; when deploying on PostgreSQL/MySQL/SQL Server, verify column types/indexes/DDL against your dialect, migration tooling, and exact artifact version. Never guess column names and configure a repository against an unverified handwritten DDL.

### 7.1. JDBC Dependencies

In Spring Boot 3.5.x Servlet:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2' // Local H2 example only; choose a real driver for production
}
```

You can use Flyway/Liquibase or your organization's migration tool. Spring Security does not automatically turn a service bean into a full migration system. Schema rollout must be controlled in multi-node deployments; do not let every node run conflicting DDL simultaneously.

### 7.2. Understanding Cleanup

`JdbcOneTimeTokenService` has `cleanupExpiredTokens()` and `setCleanupCron(String)`; the API documentation describes a periodic default cleanup schedule that can be changed or placed under a dedicated admin scheduler. Cleanup only frees storage; it **must not** replace checking expiry right at consume time.

If a token has expired but the record has not yet been deleted, `consume` must still treat it as invalid. If a token has already been consumed successfully, never rely on later cleanup to prevent replay.

### 7.3. Production JDBC Does Not Automatically Solve All Risks

Sharing a database lets both node A and B see the same record, but you must still measure:

- Transaction isolation and **atomic claim/consume** across concurrent requests.
- DB query/index cost on tokens, contention, TTL cleanup, and latency.
- Protection of token data in the DB, backups, replicas, logs, and query tracing.
- Ensuring email delivery after generation does not expose tokens in queues or logs.
- Policy for issuing multiple tokens for one user: allow multiple unexpired tokens or revoke old tokens on reissue? This is a business choice and cannot be inferred from the class name.

Inspect how the JDBC implementation of your **exact Spring Security version** handles transactions and protects tokens at rest. Never assume an implementation hashes/HMACs tokens before storage unless that version's documentation guarantees it.

## 8. "Single-Use" Is an Atomic Requirement: Stopping Two Concurrent Requests

### 8.1. Classic Race Condition

A flawed custom service might do:

```java
// PSEUDOCODE - UNSAFE, DO NOT USE IN PRODUCTION.
Token row = repository.findByValue(rawToken);
if (row != null && !row.isUsed() && row.getExpiresAt().isAfter(now)) {
    repository.markUsed(row.getId());
    return row;
}
return null;
```

Two requests A/B can both read `isUsed=false` before either updates it. Both can be accepted, breaking single-use. `synchronized` in a single JVM also fails to protect across multiple replicas.

```text
Time    Request A                 Request B
 t1     READ token: unused
 t2                               READ token: unused
 t3     UPDATE used=true
 t4                               UPDATE used=true
 t5     return valid              return valid   <- REPLAY SUCCEEDS
```

### 8.2. Claiming the Token in a Single Atomic DB Operation

With PostgreSQL, **dialect-specific SQL illustration**, one custom solution is to delete the record and return its data only if it is still unexpired:

```sql
-- Custom design example; NOT the default SQL of JdbcOneTimeTokenService.
DELETE FROM app_login_tokens
WHERE token_hash = :token_hash
  AND expires_at > CURRENT_TIMESTAMP
RETURNING user_id, tenant_id, expires_at;
```

One row can only be successfully deleted by one transaction; the next request has no row left to return. This statement assumes the token is looked up by hash/HMAC and the table data is valid. Other SQL designs may use `SELECT ... FOR UPDATE` inside a transaction followed by `DELETE`, or a conditional `UPDATE ... WHERE consumed_at IS NULL ... RETURNING` depending on the DB. Never split read/check/write into independent operations without a transaction or contention condition.

**Account check at login time:** a token may be consumed before `UserDetailsService` discovers the user has been locked/deleted; in that case, the token is burned and login fails. This is safe fail-closed behavior, not a reason to restore an already-consumed token.

### 8.3. Invariants to Put in Tests

1. `generate` returns a non-null token with username/expiry/value.
2. Consuming a valid token returns the right username **only once**.
3. Consuming the same token again afterward returns `null` (or `Mono.empty()` in reactive).
4. Consuming a non-existent/invalid value must fail and create no authentication.
5. An expired token must fail even if the record has not been cleaned up yet.
6. Two competing consume requests for the same token have **exactly one winner** across all involved instances/nodes.
7. Behavior at the exact `expiresAt` boundary must be consistent.
8. A token for user A cannot be replayed/switched to user B via a request parameter.

## 9. Protecting Tokens at Rest, in Transit, and on Display

### 9.1. Should Raw Tokens Be Stored?

If an attacker reads a database containing unused raw tokens, they can hijack future sessions within the TTL. For a **custom service**, consider storing an **appropriately designed digest**, such as `HMAC-SHA-256` with a separately protected server-side secret/pepper, or SHA-256 when the raw token truly has sufficient entropy and the threat model permits it. Look up tokens by digest, not cleartext:

```text
raw token  --HMAC with server secret--> token_hash
             |                              |
       deliver to user              persist in database
       (do not log)                 (do not store raw token)
```

Things to plan for in custom storage:

- Keep the HMAC key/pepper in a secret manager, not in DB dumps; support rotation and versioning.
- The raw token still travels through the delivery channel, but must never enter metrics, exception text, audit logs, or tracing spans.
- Query by digest with a proper index; compared to a plaintext store, measure performance and enforce backup/replica protection policies.
- Use one consistent digest method for generate/consume, never `String.hashCode()` (not a cryptographic hash).
- If a token has low entropy, hashing alone will not save it from brute force; increase entropy first.

**Do not claim default `JdbcOneTimeTokenService` uses HMAC** unless you have verified the source of the deployed version. A requirement to store hashed tokens may lead to writing a custom `OneTimeTokenService`.

### 9.2. Magic Links Have Tokens in URLs: Limiting Exposure

Magic links often look like:

```text
https://accounts.example.org/login/ott?token=<secret>
```

The value after `?token=` is a sensitive credential. It can appear in browser history, reverse-proxy access logs, referrer headers, email security scanners, screenshots, or analytics. Design for this:

- Enforce HTTPS on public domains; validate the public base URL from trusted configuration instead of concatenating an unchecked request `Host`.
- Restrict/scrub query logging in proxies/apps; do not send tokens to analytics or tracking systems.
- Pages containing the token must avoid third-party scripts, pixels, and external images; use `Referrer-Policy: no-referrer` or a strict policy.
- `GET /login/ott?token=...` should only **display the form** and populate the token into it; **`POST /login/ott` is the step that actually consumes** in the default flow. This reduces the risk of email link previewers/bots opening GET and consuming the token.
- A valid CSRF token is still needed for POST per Spring Security configuration; do not disable CSRF application-wide for magic links.
- After login, redirect to a clean URL and remove the token from the address bar via an appropriate frontend flow; do not leak credentials into arbitrary referrer/Location headers.
- Short TTL, single-use, and rate limiting on generation/consumption to prevent high-speed token guessing.

Never promise "the URL is completely secret" when browser/email technologies still have leakage surfaces; minimize lifetime and logging exposure everywhere.

## 10. Spring Security Servlet: Integrating with Forms and Filters

### 10.1. DSL

Spring Security 6.5 supports:

```java
// Snippet inside SecurityFilterChain; formLogin is optional for demo UI.
http
    .formLogin(Customizer.withDefaults())
    .oneTimeTokenLogin(ott -> ott
        .tokenGenerationSuccessHandler(myHandler));
```

Core filters/components typically include:

- `GenerateOneTimeTokenFilter` accepts `POST /ott/generate` by default, creates `GenerateOneTimeTokenRequest`, and calls the service.
- `OneTimeTokenGenerationSuccessHandler` receives the generated token to deliver it (email/SMS) and return a generic response.
- `DefaultOneTimeTokenSubmitPageGeneratingFilter` serves `GET /login/ott` to display the token entry page, pre-filling if the query contains `token`.
- `OneTimeTokenAuthenticationFilter` processes `POST /login/ott` (with CSRF per policy) and creates an authentication request.
- `OneTimeTokenAuthenticationProvider` uses the service to **consume**, then uses `UserDetailsService` to authenticate the user and load authorities.
- `SecurityContext` and session are created/managed by the security chain just like any normal successful login.

**Distinguish GET and POST:** the magic link URL `GET /login/ott?token=...` should not be treated as already signed in; the form's POST triggers authentication. If writing a custom submit page, remember to send both the token and the CSRF token. Do not write a GET controller that consumes the token just to skip a step, because mail scanners/crawlers can open the link.

### 10.2. A Service Bean Alone Does Not Send Email

If you only configure:

```java
http.oneTimeTokenLogin(Customizer.withDefaults());
```

Spring Security cannot know which user has which email address or how to send mail. Register a `OneTimeTokenGenerationSuccessHandler` or specify it directly in the DSL; control the username → verified email mapping in a trusted directory. `OneTimeTokenService` should not be overloaded with sending emails, rendering HTML, redirecting browsers, or creating sessions.

## 11. Complete Spring Boot Servlet Demo: Generating Tokens and Sending via Local SMTP

This is a **Spring Boot 3.5.x + Spring Security 6.5.x, Java 17+** demo for a single user `alice`. It uses the default in-memory service; email delivery goes to a local **mail testing server**. The demo separates generation/storage (Spring) from delivery (application), without returning raw tokens in HTTP responses. To run end-to-end, an SMTP capture server must listen on port `1025` (e.g., Mailpit/MailHog) with a demo mailbox; settings/URLs below are for localhost only.

### 11.1. Gradle Dependencies

In a Spring Boot project with the Boot plugin and suitable Java toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

### 11.2. application.yml

Save `src/main/resources/application.yml`:

```yaml
server:
  port: 8080
spring:
  mail:
    host: localhost
    port: 1025
app:
  ott:
    base-url: "http://localhost:8080"
    recipient: "alice@example.test"
```

When deploying to production, `base-url` must be a configured/controlled public HTTPS hostname, `recipient` must come from the account's **verified** email record, and SMTP must have authentication/TLS policies. Do not use a constant `alice@example.test` to send mail for every username.

### 11.3. Java Source

Place in `src/main/java/demo/ott/OttApplication.java`:

```java
package demo.ott;

import java.security.Principal;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@SpringBootApplication
public class OttApplication {

    public static void main(String[] args) {
        SpringApplication.run(OttApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}local-demo-only")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    OneTimeTokenGenerationSuccessHandler magicLinkMailer(
            MailSender mailSender,
            @Value("${app.ott.base-url}") String baseUrl,
            @Value("${app.ott.recipient}") String demoRecipient) {

        return (request, response, oneTimeToken) -> {
            // Demo only has account alice; responses for all usernames are identical.
            if ("alice".equals(oneTimeToken.getUsername())) {
                String magicLink = UriComponentsBuilder
                        .fromUriString(baseUrl)
                        .path("/login/ott")
                        .queryParam("token", oneTimeToken.getTokenValue())
                        .build()
                        .encode()
                        .toUriString();

                SimpleMailMessage message = new SimpleMailMessage();
                message.setFrom("no-reply@example.test");
                message.setTo(demoRecipient);
                message.setSubject("Your one-time sign-in link");
                message.setText("Open the following link to sign in: "
                        + magicLink);

                mailSender.send(message);
            }
            response.sendRedirect(request.getContextPath() + "/ott/sent");
        };
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            OneTimeTokenGenerationSuccessHandler magicLinkMailer)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/ott/sent", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(ott -> ott
                        .tokenGenerationSuccessHandler(magicLinkMailer))
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String home() {
            return "Visit /login to request a one-time sign-in link.";
        }

        @GetMapping("/ott/sent")
        String sent() {
            return "If the account is eligible, a sign-in link was sent.";
        }

        @GetMapping("/private")
        String privatePage(Principal principal) {
            return "Hello, " + principal.getName();
        }
    }
}
```

**Explanation:**

- Default `OneTimeTokenService` is selected by Spring Security when no separate service bean is declared. It creates/stores the token; the mail handler only receives the generated token.
- `OneTimeTokenGenerationSuccessHandler` builds the URI from **server configuration**, avoiding trusting an arbitrary `Host` header when creating links; it sends the link to the demo recipient and redirects to a generic notice page.
- `UserDetailsService` resolves user `alice`; once a token is consumed successfully, Spring Security still looks up user/authorities.
- `password("{noop}...")` is strictly for local illustration and form login support; magic links do not rely on sending passwords in email. Production uses an appropriate password encoder or a dedicated passwordless design.
- This demo **lacks rate limiting, delivery retry/outbox, and production SMTP**. An SMTP error will fail the generation request, while the created token may remain in storage until expiry; dedicated delivery error handling is needed in production.
- `/ott/sent` returns the same message to reduce account-existence leaks; if SMTP errors produce different responses between existing and non-existing users, handle them so responses remain uniform.
- Do not log URLs or tokens. A local mail capture UI is only for inspection on dev machines; do not expose real tokens in screenshots or analytics.

### 11.4. Running and Observing

Start an SMTP test server on `localhost:1025` using your preferred tool, then run:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`. Open `http://localhost:8080/login` and submit a **token generation request** for username `alice` using the Spring Security-generated form. Check your email capture tool for the magic link; open it:

```text
http://localhost:8080/login/ott?token=<value-from-test-email>
```

The default submit page detects the `token` query parameter and populates the form. Submit a valid POST with the CSRF token to sign in; on success, call `GET /private` and expect the body:

```text
Hello, alice
```

Reopen the link and submit it again **in a clean browser session**: the already-used token must be rejected. There is no fixed stdout for the generate step because token values are randomly generated. If you are **already signed in** and reopen the old token, your active session state can mask the result; use incognito or sign out to test the real auth flow.

For non-existent users, the demo handler sends no email and redirects to the same notice. This illustrates a generic response, without guaranteeing that timing/network patterns are completely immune to user enumeration.

## 12. Separating Interface from Implementation: Custom OneTimeTokenService

You should write a custom service when you need one or more of the following:

- Storing **digest/HMAC** instead of raw tokens.
- Storing in PostgreSQL/Redis with atomic transactions/Lua/conditional updates.
- Enforcing TTLs, per-tenant context, purpose binding, or a policy revoking old tokens on reissue.
- Enforcing per-user unused token limits, lifecycle monitoring, or audit metadata.
- Multi-instance synchronization and safe digest key rotation.

A minimal design for a custom service (**pseudo API only**, does not compile directly):

```java
// PSEUDOCODE: sketches responsibilities, not a runnable Java file.
OneTimeToken generate(GenerateOneTimeTokenRequest request) {
    String secret = secureRandomBase64Url();
    Instant expiresAt = clock.instant().plus(request.getExpiresIn());
    repository.insert(
            hmacSha256(secret), request.getUsername(), expiresAt);
    return new DefaultOneTimeToken(
            secret, request.getUsername(), expiresAt);
}

OneTimeToken consume(OneTimeTokenAuthenticationToken authentication) {
    String digest = hmacSha256(authentication.getTokenValue());
    // One atomic DB command: only claims an unexpired and unused row.
    StoredToken claimed = repository.deleteAndReturnIfValid(digest);
    if (claimed == null) {
        return null;
    }
    return new DefaultOneTimeToken(
            authentication.getTokenValue(),
            claimed.username(), claimed.expiresAt());
}
```

**Implementation constraints that must be satisfied:**

1. Generate must persist the record successfully before returning the token to the success handler. If the DB insert fails, do not send a link promising it works.
2. `consume` must never "check first and mark later" in two non-transactional operations.
3. Beyond TTL, check `purpose`, tenant, session binding, and account status per application contract. Never reuse digests from other token types in the same namespace.
4. Do not embed email sending inside a DB transaction holding long row locks; use an outbox/queue when reliability is needed.
5. Never return `DefaultOneTimeToken` after a database update without checking the affected row count.
6. Agree on whether generating a new token leaves old tokens valid or revokes them; reflect this clearly in the schema and tests.
7. Hashing/HMAC/secret rotation/expiry checks must be consistent across all nodes.

The pseudo example is not code to copy straight into a project: `repository`, `secureRandomBase64Url`, and `hmacSha256` here are abstractions you must implement and test yourself.

## 13. Reactive WebFlux: ReactiveOneTimeTokenService

WebFlux applications use a **different** interface in the `org.springframework.security.authentication.ott.reactive` package:

```java
// Reactive contract shape, for explanation.
public interface ReactiveOneTimeTokenService {
    Mono<OneTimeToken> generate(GenerateOneTimeTokenRequest request);
    Mono<OneTimeToken> consume(OneTimeTokenAuthenticationToken authenticationToken);
}
```

Key difference: an invalid token is represented by **`Mono.empty()`**, not the `null` of the Servlet interface. Default `InMemoryReactiveOneTimeTokenService` is only suited for single-process storage; applications needing a distributed DB can implement it with R2DBC/a reactive client while preserving atomicity.

### WebFlux Configuration

```java
// Snippet in a @Configuration class with @Bean and matching imports.
@Bean
SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/", "/ott/sent").permitAll()
                    .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults())
            .build();
}
```

To replace the service, declare a `@Bean ReactiveOneTimeTokenService` or call `.oneTimeTokenLogin(ott -> ott.tokenService(customReactiveService))` per your version's API. To send magic links in a reactive application, implement `ServerOneTimeTokenGenerationSuccessHandler`:

```java
// Handler interface snippet:
Mono<Void> handle(ServerWebExchange exchange, OneTimeToken token);
```

Email delivery must use a true reactive client or be isolated off the event loop per policy; never call blocking SMTP/JDBC directly inside a WebFlux handler. If a blocking email library is unavoidable, use `Mono.fromRunnable(...).subscribeOn(Schedulers.boundedElastic())` inside a properly composed publisher; never call `subscribe()` and return success before sending completes.

**Do not** wrap synchronous Servlet `JdbcOneTimeTokenService` and `UserDetailsService` in `Mono.just(...)` inside a WebFlux pipeline and call it reactive. Reactive persistence/identity lookup must be designed and configured separately.

## 14. Unit Testing with InMemoryOneTimeTokenService: Single-Use Lifecycle

To test the API directly, include in your Gradle Spring Boot project:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Create `src/test/java/demo/ott/OneTimeTokenServiceTest.java`:

```java
package demo.ott;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest;
import org.springframework.security.authentication.ott.InMemoryOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.authentication.ott.OneTimeTokenAuthenticationToken;

import static org.junit.jupiter.api.Assertions.*;

class OneTimeTokenServiceTest {

    @Test
    void tokenCanBeConsumedExactlyOnce() {
        var service = new InMemoryOneTimeTokenService();
        OneTimeToken issued = service.generate(
                new GenerateOneTimeTokenRequest(
                        "alice", Duration.ofMinutes(5)));

        var request = OneTimeTokenAuthenticationToken
                .unauthenticated(issued.getTokenValue());

        OneTimeToken first = service.consume(request);
        OneTimeToken second = service.consume(request);

        assertNotNull(first);
        assertEquals("alice", first.getUsername());
        assertNull(second);
    }

    @Test
    void expiredTokenIsRejected() {
        var service = new InMemoryOneTimeTokenService();
        Instant t0 = Instant.parse("2026-01-01T10:00:00Z");
        service.setClock(Clock.fixed(t0, ZoneOffset.UTC));

        OneTimeToken issued = service.generate(
                new GenerateOneTimeTokenRequest(
                        "alice", Duration.ofSeconds(30)));

        service.setClock(Clock.fixed(
                t0.plusSeconds(31), ZoneOffset.UTC));

        var request = OneTimeTokenAuthenticationToken
                .unauthenticated(issued.getTokenValue());

        assertNull(service.consume(request));
    }

    @Test
    void unknownTokenIsRejected() {
        var service = new InMemoryOneTimeTokenService();

        var request = OneTimeTokenAuthenticationToken
                .unauthenticated("missing-token");

        assertNull(service.consume(request));
    }
}
```

Run:

```bash
./gradlew test --tests demo.ott.OneTimeTokenServiceTest
```

Expect **three tests PASS** with matching Spring Security 6.5/Boot 3.5 dependencies. The tests use `Clock.fixed(...)` to avoid `Thread.sleep` and make expiry deterministic; these are unit tests of the default in-memory service and **do not prove** real database/JDBC behavior or email delivery.

An additional concurrency test should generate one token and launch multiple threads calling `consume` behind a barrier, asserting that the total number of non-null returns is **1**. For multi-instance persistence, run the same test across two separate processes targeting a shared DB; a single-JVM test cannot prove cross-node atomicity.

## 15. Integration Testing Generate, Delivery, and Login

To verify the full flow works, test what service unit tests do not cover:

| Scenario | How to Trigger | Criteria |
| --- | --- | --- |
| Valid generate | Submit `POST /ott/generate` with CSRF token | One token created/stored, handler sends to right verified contact |
| Non-existent username | Submit a non-existent identifier | Generic response, no account existence leaked via body/status/obvious timing |
| Fresh magic link | Open link, submit valid `POST /login/ott` | Eligible user signs in; authorities match |
| Replay | Submit already-used token again in a new session | No new authentication created |
| Expiry | Set short clock/TTL and submit after expiry | Not authenticated even if record is not cleaned up |
| Wrong token | Alter one character of the token | Not authenticated; no detailed reason leaked |
| Two concurrent requests | Submit the same token in parallel | Exactly one request succeeds |
| Restart/replica | Generate A, consume B; restart mid-way | Memory loses token; shared JDBC behaves per policy |
| Account locked after generate | Lock user before consume | Login rejected; no privilege escalation |
| SMTP failure | Simulate mail service timeout/5xx | Do not return token in response; have metrics/fallback; record expires or is revoked |
| Mail preview bot | Bot only GETs the link | Token **not yet consumed** when using standard form POST flow |
| CSRF | POST generate/login missing token per policy | Blocked; never silently disable all CSRF |
| Token/URL logging | Inspect proxy/app/observability | No raw token recorded in logs/traces |
| Email change/tenant | Same username across tenants, unverified email | Does not send or misbind identity |
| Multiple pending tokens | Generate 2 links for one user | Rule allowing multiple or invalidating old tokens is verified |

You can use `MockMvc` and `spring-security-test` to check filters/controllers/CSRF, but a fake mail server and real database require dedicated integration tests. Tests must assert the **authentication outcome**, not just redirect status or that an email was sent.

## 16. Common Errors and How to Handle Them

### "Token generates fine, but clicking the link does not sign in"

Check whether the GET `/login/ott` form exists and whether the browser submits **POST `/login/ott`** with valid token/CSRF. Do not assume GET already consumed the token. Check that the username stored in the token matches `UserDetailsService` and the account is not disabled/locked. In multi-replica setups, check whether generate/consume hit two JVMs using the memory service.

### "Token can sign in twice"

Inspect whether you check the token via `findByValue` and then call `markUsed`. Lack of atomicity leads to replay under concurrency. Fix it in storage transactions/conditional updates, not just by adding an `isUsed` check in a controller. For sequential duplicate POSTs, the default service must return invalid after the first use.

### "Expired tokens remain in the DB"

Cleaning up expired records is not what decides validity. Check the `Instant` comparison in consume, cleanup cron, node clocks, and TTL policy. Avoid subtracting/converting time zones with locale strings.

### "Works locally, tokens disappear randomly in production"

Default `InMemoryOneTimeTokenService` does not share state across nodes and loses data on restart. Use JDBC/shared store or a justified routing/lifecycle choice; run multi-instance integration tests.

### "Application sends email for a username without an account"

Separate verified account/contact lookup inside the delivery handler/directory. Keep the request response generic to reduce enumeration. Never automatically send mail to an email string entered by the user just because it matches `getUsername()`.

### "Magic link gets consumed by bots/email filters"

Check if a custom GET endpoint auto-consumes. Keep GET strictly to rendering the submit page and use POST to authenticate; design extra defenses if mail providers perform form submissions or aggressive prefetching. Configure TTL/rate limits and avoid embedding third-party tracking in email templates.

### "Token leaked in logs"

Check reverse proxy query logging, Java access logs, tracing, Sentry, browser monitoring, mail capture, and exception handlers. A raw token is a credential; never log `getTokenValue()`, echo it in responses, or expose full URLs. Set `Referrer-Policy`, TLS, and clean post-login URLs.

### "Changed TTL, but token still only lives 5 minutes"

Construct the request with the right duration, or configure Spring Security's request resolver per your version's API. With a custom service, verify the service actually honors `request.getExpiresIn()` and all nodes have synced clocks; do not merely change the text in the email.

### "Using JdbcOneTimeTokenService throws table not found"

The standard classpath schema has not been applied or migrations have not run on the right database/schema. Check datasource, SQL dialect, database permissions, and migration version; do not assume Boot auto-creates the table just because a JDBC bean exists.

### "Email delivered, yet login reports invalid"

The token may have expired, been consumed earlier, suffered a DB transaction rollback, had the link truncated/mis-encoded, or the memory store restarted after sending. Inspect logs **that contain no tokens**, using correlation IDs/properly hashed token record IDs to diagnose.

## 17. Production Checklist Before Enabling One-Time Token Login

1. **Right version configuration:** Spring Security ≥ 6.4 using `oneTimeTokenLogin` with the matching Servlet/Reactive API; verify method signatures from actual-version Javadoc.
2. **Token issuance:** `SecureRandom` or an implementation with sufficient entropy, short TTL, proper username/tenant/purpose, and per-user/IP request limits.
3. **Storage:** choose a shared store for multiple replicas, evaluate backup/replication, expiry cleanup, transaction isolation, and atomic consume.
4. **At rest:** consider digest/HMAC and key rotation; do not assume default JDBC stores hashes; protect DB access, backups, and query logs.
5. **Delivery:** send only to verified contacts, prevent user enumeration, monitor SMTP/outbox failures; never return raw tokens to the requester.
6. **Request flow:** POST generate/submit with CSRF per policy; GET magic link only renders the form; prevent email scanners from consuming tokens.
7. **Browser/security headers:** HTTPS, registered/trusted domain, Referrer-Policy, strict CSP, and no third-party scripts/pixels on token-bearing pages.
8. **Authentication:** after consume, still check user/account state and authorities; never take a username from the consume request body to replace the record's identity.
9. **Replay:** test 2+ concurrent requests and multiple nodes; never allow a used token to "resurrect" via retry/transaction rollback.
10. **Expiry/reissue:** specify clearly what happens to old tokens when a new link is created, clock source, cleanup, notifications, and locked-account handling.
11. **Logging:** do not log tokens, full magic links, sensitive emails/phones, or security credentials; emit safe metrics for generate/send/use/failure.
12. **Testing:** service JUnit tests, web filters/CSRF, delivery, restarts, race conditions, DB failover, timeouts, and user enumeration.
13. **Monitoring:** track generate/send/consume success rates, expired token counts, blocked replays, mail latency, and storage errors.

**Bottom line:** `OneTimeTokenService` is responsible for **creating and managing token lifecycle**, `OneTimeTokenGenerationSuccessHandler` is responsible for **delivering the token**, and `OneTimeTokenAuthenticationProvider` is responsible for **using the consumed token to authenticate the account**. Single-use is guaranteed by the atomic consume operation in storage, not merely by a UI flag.

## 18. Official Documentation

- [Spring Security 6.5 – One-Time Token Login (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html): DSL, login page, generate/submit, sending magic links, custom services.
- [OneTimeTokenService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/OneTimeTokenService.html): exact `generate`/`consume` signatures.
- [GenerateOneTimeTokenRequest API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/GenerateOneTimeTokenRequest.html): username and expiration duration.
- [OneTimeTokenAuthenticationToken API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/OneTimeTokenAuthenticationToken.html): credential used during consume.
- [OneTimeToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ott/OneTimeToken.html): token value, username, expiresAt.
- [InMemoryOneTimeTokenService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/InMemoryOneTimeTokenService.html): UUID, in-memory behavior, and `setClock`.
- [JdbcOneTimeTokenService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/JdbcOneTimeTokenService.html): JDBC schema, `cleanupExpiredTokens`, and cleanup schedule.
- [OneTimeTokenAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ott/OneTimeTokenAuthenticationProvider.html): consume token and load user/authorities.
- [Spring Security 6.5 – One-Time Token Login (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/onetimetoken.html): ReactiveOneTimeTokenService and ServerOneTimeTokenGenerationSuccessHandler.
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): recommendations for protecting one-time links/tokens, TTL, generic responses, and brute-force limits.
