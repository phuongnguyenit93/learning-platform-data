# Responses, processing time, and the risk of account enumeration

## 1. Objectives and scope

An authentication application may protect passwords with BCrypt, enable HTTPS, lock accounts, and enforce MFA yet still accidentally reveal **which accounts exist**. An attacker does not necessarily need to log in successfully: merely distinguishing two outcomes when submitting an email address or username lets them build a user list for password spraying, phishing, social engineering, or follow-on attacks.

This flaw is called **account enumeration / username enumeration**. The disclosure channel is not just a message like "Email not registered"; it can be **HTTP status, redirects, response content/length, response headers, cookies, UI behavior, processing steps, response timing, rate limits, email side effects**, or differences across other services.

Learning objectives after this lesson:

1. Explain account enumeration and distinguish it from password testing or brute force.
2. Identify **discrepancy factors** across all login, registration, and recovery flows.
3. Understand why an identical message string **is not enough** if fast/slow processing paths differ.
4. Understand `DaoAuthenticationProvider`, `UserDetailsService`, `PasswordEncoder`, `hideUserNotFoundExceptions`, and Spring Security's built-in timing-leak mitigation.
5. Design generic public responses, asynchronous email/reset processing, rate limiting, and internal logging without leaking information.
6. Write a Spring Boot 3.x, Spring Security 6.x, Java 17+ example and unit/integration tests for anti-enumeration defenses.
7. Evaluate limitations: the difficulty of achieving **strictly identical** timing over a network, UX trade-offs, and denial-of-service risks from misapplied countermeasures.

**Scope:** **Spring Security Servlet/Spring MVC** applications, especially username/password and forgot-password flows; extending to OTT, OTP, SSO, REST, GraphQL, APIs, and account registration. Spring Security 7.x carries these core concepts forward; main configuration examples use Spring Security 6.5 / Spring Boot 3.x.

## 2. How does account enumeration work?

Imagine two requests to the same endpoint:

```http
POST /login
Content-Type: application/x-www-form-urlencoded

username=alice&password=invalid-password
```

```http
POST /login
Content-Type: application/x-www-form-urlencoded

username=does-not-exist&password=invalid-password
```

If one request returns **"Incorrect password"** and the other returns **"Account not found"**, an outsider has an oracle to classify usernames without knowing any password.

Even if both return:

```json
{"error":"INVALID_CREDENTIALS"}
```

information can still leak:

```text
Username exists          -> DB lookup + BCrypt.matches(...) -> slow response
Username does not exist  -> DB lookup + immediate return    -> fast response
```

An observer can repeat probes, filter noise, and infer two latency distributions. This is a **timing side channel**.

**Distinguishing objectives:**

| Issue | What does the attacker want to know/do? | Data needed |
| --- | --- | --- |
| Account enumeration | Determine whether a user/email exists in the system | One username and differences in responses |
| Password guessing | Find the right password for one account | Password set |
| Password spraying | Try a few common passwords across many accounts | Many usernames; enumeration boosts efficiency |
| Credential stuffing | Try username/password pairs leaked from another system | Credential list |
| Account takeover | Seize control of an account | May combine enumeration, reset, phishing, leaked sessions |

Reducing enumeration shrinks the attack surface, but **does not replace** MFA, strong passwords, rate limits, anomalous login alerts, and account takeover controls.

## 3. Places that easily leak account existence

A product has many identity-checking paths, not just `/login`.

| Flow / endpoint | Dangerous signal | Response approach to consider |
| --- | --- | --- |
| Form login | "User does not exist" differs from "Wrong password" | Generic failure message |
| REST `/api/auth/login` | 404 when user is absent, 401 when password is wrong | Same status/body for invalid credentials |
| Forgot password | "Email is not registered" | "If a matching account exists, instructions will be sent" |
| Magic link/OTT request | "Sent link to alice", or differing status | Generic request-accepted response; deliver token only to verified channel |
| Send OTP/SMS code | "Phone number is not linked to an account" | Do not publicly confirm account/phone linkage |
| Account registration | "Email already used" vs "Account created" | Consider verifying email before disclosing info or use generic confirmation flow |
| Organization/SSO registration | Different redirect when tenant/email exists | Constrain legitimate routing, avoid leaking membership |
| WebAuthn/passkey login | Showing "No passkey for this user" | Use non-disclosing flows where feasible and control fallbacks |
| Recovering MFA backup codes | Reveals whether account has MFA/TOTP enabled | Do not disclose factor status before verifying access rights |
| Username check API | Public `available` boolean | Treat as an enumeration vector; add rate limits and disclosure policy |
| GraphQL | `USER_NOT_FOUND` differs from `INVALID_PASSWORD` in `errors.extensions` | Standardize public error codes for auth operations |
| Support chat/help desk | Agent confirms "This email is in the system" | Caller verification process, restrict sharing membership |

**Securing `/login` alone does not mean other endpoints are protected.** In particular, password reset and magic-link features are frequent enumeration paths because UI designs tend to over-explain.

## 4. Discrepancy factors: not just the message string

Application builders often fix only the text message, yet external callers observe the **entire HTTP exchange**.

| Observation layer | Example difference when user exists vs does not exist |
| --- | --- |
| Status code | `200` vs `404`, `401` vs `403` |
| JSON fields | `{ "reason": "USER_NOT_FOUND" }` vs `{ "reason": "WRONG_PASSWORD" }` |
| HTML | Different error block; "Recovery hint" content shown only for valid users |
| Body length | 180 bytes vs 326 bytes, even if visible text looks similar |
| HTTP headers | Differing `Location`, `WWW-Authenticate`, `Cache-Control`, `Content-Type` |
| Cookies | `Set-Cookie`/session changes only when the username exists |
| Redirect chain | Redirect to `/verify-otp` only for valid accounts before password verification |
| Timing | Skipping password hash when account is not found |
| Downstream calls | Calls mail/CRM/LDAP if account exists; returns immediately if absent |
| Rate limit | Only valid accounts get `429` after a number of attempts |
| Side effects | Sending email/SMS, push notifications, state changes, or different audit writes |
| Localized UI | Vietnamese and English show different errors per branch |
| API error details | Stack traces, exception types, `error_description` exposing account state |

**Consistent responses** must be evaluated at the level of **what an outsider actually sees**: status, headers, body, cache behavior, redirects, relative timing, and interactive behavior. There is no mandatory rule that every system error must return `401`: **invalid credentials** must be distinguished from **infrastructure outages** under a deliberate policy.

Example of a consistent login error response for non-existent account, wrong password, locked account, or disabled account:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
Cache-Control: no-store

{"error":"INVALID_CREDENTIALS"}
```

This is an **illustrative format** for an API; a form UI may consistently redirect to `/login?error` instead of returning JSON. The rule is not "every response is 401", but that **causes that should not be publicly distinguished** must be handled consistently.

## 5. Public messages vs internal log information

### Login

**Avoid:**

```json
{"error":"USER_NOT_FOUND","message":"Account does not exist"}
```

```json
{"error":"WRONG_PASSWORD","message":"Incorrect password"}
```

**Use** a single generic error:

```json
{"error":"INVALID_CREDENTIALS","message":"Invalid credentials"}
```

Locked/disabled cases must also be considered to avoid disclosing state before the user proves ownership. However, you still need **sufficiently helpful notices via a trusted channel** when a real user needs account recovery. For example, after verifying the registered email channel, the user can receive detailed instructions without exposing them to strangers on the login form.

### Forgot password

**Avoid:**

```text
This email address was not found.
```

**Use:**

```text
If a matching account exists, recovery instructions will be sent to the registered channel.
```

Never return the reset token or link to the requester. Delivery goes to the **verified email/phone belonging to the account**, not a new address typed by the requester to gain access to someone else's account.

### Registration

A user trying to sign up with an already-used email is a real UX problem: sometimes you need to indicate the username is taken. Weigh the business model and sensitivity of membership. One option is replying "Please check your inbox if the address is eligible" and handling **new signup / controlled recovery** via email, without publicly confirming the address already has an account. For publicly visible usernames, limited availability checks with rate limiting may be acceptable; never generalize that policy to private emails or sensitive personnel rosters.

### Logging

Internally, operations may need failure reasons: `USER_NOT_FOUND`, `BAD_PASSWORD`, `LOCKED`, `DISABLED`, `RATE_LIMITED`, `BACKEND_ERROR`. However:
- Never log passwords, OTPs, reset tokens, raw session IDs, or Bearer tokens.
- Avoid writing raw emails/usernames into broadly accessible logs; use internal IDs or controlled pseudonymized values where appropriate.
- Prevent log injection/CRLF from input; use structured logging.
- Keep log read permissions narrow; enforce policy-based retention and auditing.
- **Never reflect** internal reasons into responses/headers/GraphQL error extensions.

## 6. Timing side channel: why identical messages still leak

Illustration of a flawed processing path:

```text
POST /login
  |
  +--> look up username in DB
          |
          +-- does not exist --> return error immediately (very fast)
          |
          `-- exists --> compute BCrypt.matches(...) (takes time)
                             |
                             `--> return same public error
```

Passwords are stored with intentionally **CPU/memory-expensive** hashing algorithms (BCrypt/Argon2/PBKDF2 per policy). When the username exists, `PasswordEncoder.matches` takes noticeable time. When the username is absent and code returns immediately, the gap can be large enough to observe statistically, even with identical HTTP bodies.

**Reverse signals** can also occur:
- Only valid accounts traverse status-checking services, MFA providers, or LDAP.
- Valid accounts receive sessions/cookies/captchas while missing accounts return immediately.
- Valid accounts send email synchronously over SMTP.
- Locked accounts execute a different DB update/transaction.
- Some backends keep hot caches for popular accounts and take a different lookup path for wrong usernames.
- Timeout/LDAP bind errors happen only when the user exists.

**There is no guarantee every request has identical latency over the Internet.** Networks, load balancers, GC, caches, traffic, and schedulers create noise. The practical goal is **eliminating systematic, easily exploitable gaps** between public branches, not promising nanosecond-equal `time_total` on every request.

## 7. What does Spring Security's `DaoAuthenticationProvider` do?

In a typical username/password flow:

```text
UsernamePasswordAuthenticationFilter
             |
             v
ProviderManager (AuthenticationManager)
             |
             v
DaoAuthenticationProvider
       |
       +--> UserDetailsService.loadUserByUsername(username)
       |
       +--> PasswordEncoder.matches(rawPassword, encodedPassword)
       |
       +--> Check UserDetails status, create Authentication or error
             |
             v
AuthenticationFailureHandler / HTTP response
```

`DaoAuthenticationProvider` uses `UserDetailsService` to find the account and `PasswordEncoder` to compare passwords. `UserDetailsService` **must throw `UsernameNotFoundException`** when the account does not exist; returning `null` violates the contract and causes an internal error.

### 7.1. `hideUserNotFoundExceptions` defaults to `true`

`AbstractUserDetailsAuthenticationProvider` (superclass of `DaoAuthenticationProvider`) has `setHideUserNotFoundExceptions(boolean)`.

By default, whether the username does not exist **or** the password is wrong, callers see a generic `BadCredentialsException`; setting `false` exposes a more specific `UsernameNotFoundException` when the username is absent. Setting `false` is described by the Javadoc as **less secure**.

Avoid configuring:

```java
// Not recommended on public login services:
provider.setHideUserNotFoundExceptions(false);
```

Even when masking exception names, an app with a custom `AuthenticationFailureHandler` can still leak differences if it inspects internal exceptions, calls external services, or returns differing redirects/statuses. Inspect the entire pipeline, not just `UserDetailsService`.

### 7.2. Reducing timing gaps when a username does not exist

In modern Spring Security versions, `DaoAuthenticationProvider` uses an encoded password value reserved for a **non-existent user** and still invokes `PasswordEncoder.matches(...)` on that branch instead of skipping password work altogether. This mitigates timing discrepancies (referenced under issue `SEC-2056`).

Conclusions:
- **No need** to manually insert `Thread.sleep(...)` just to "balance" the user-not-found branch when using standard `DaoAuthenticationProvider`.
- This mechanism is **not** strictly constant-time and does not automatically protect custom network/LDAP/DB/service calls.
- If overriding the provider, adding caching, using a custom encoder, or using another authentication manager, re-verify the actual execution path.
- The non-existent hash is prepared and used per implementation; do not infer a fixed hash type if using a custom `PasswordEncoder`.
- `disabled`/`locked` accounts, passwords on encoders with differing costs, or extra check hooks can still differ in timing; test against your **exact application version**.

Spring Security 7.1 introduces `setAlwaysPerformAdditionalChecksOnUser(...)`, documented in Javadoc to control certain pre-auth checks; do not assume that method name exists on 6.x.

### 7.3. Never disable password hashing to make paths equally fast

Wrong approach:

```java
// WRONG: plaintext password comparison or fast hashing does not solve security.
// if (presentedPassword.equals(account.getPassword())) ...
```

Password storage must continue using an appropriate `PasswordEncoder` (BCrypt/Argon2/PBKDF2) with work factors defending against offline attacks. Timing alignment is only **one layer** of design and must never weaken password verification.

## 8. Spring Boot 3.x + Spring Security 6.x application example

The Servlet example below shows:
- Username/password via default `DaoAuthenticationProvider`.
- Strong `PasswordEncoder` instead of `{noop}`.
- All form-login authentication failures mapped to **one status + one JSON body**.
- **Never** exposing exception classes or account statuses to the client.

This is a single-login-path demo; rate limiting, sessions, mail recovery, MFA, and monitoring policies must be added separately.

### 8.1. Dependencies

Use in `build.gradle` of a Spring Boot 3.x project with Spring Boot/Java 17+ plugins:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Never mix incompatible Spring Security major versions outside Spring Boot's BOM/Dependency Management.

### 8.2. Security configuration and failure handler

File `src/main/java/example/enumeration/EnumerationSafeSecurityConfig.java`:

```java
package example.enumeration;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class EnumerationSafeSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Hardcoded account/password ONLY for local demo.
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-password-not-for-production"))
            .authorities("ROLE_USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/account/recover").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .failureHandler((request, response, exception) -> {
                    // Do not reflect exception.getMessage().
                    response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                    response.setContentType(
                        MediaType.APPLICATION_JSON_VALUE
                    );
                    response.setCharacterEncoding(
                        StandardCharsets.UTF_8.name()
                    );
                    response.setHeader("Cache-Control", "no-store");
                    response.getWriter().write(
                        "{\"error\":\"INVALID_CREDENTIALS\"}"
                    );
                })
            );

        return http.build();
    }
}
```

**Why use `failureHandler`?** In form login, authentication errors arise in a Spring Security filter, **not** a Spring MVC controller. `@RestControllerAdvice` does not catch those exceptions by default. The `AuthenticationFailureHandler` hook is the right place to control the form-login response.

**Demo notes:**
- The handler returns JSON on the `/login` form endpoint for easier testing; an HTML app can choose a **generic redirect** instead of JSON, provided both credential failures look identical publicly.
- The demo `UserDetailsService` only has `alice`; in a real system replace it with a repository carrying full account states, and never store demo passwords in code.
- Default `formLogin` uses `POST /login` with `username` and `password` fields; with CSRF enabled, requests must include a valid CSRF token.
- Do not enable remember-me or HTTP Basic just to "make testing easier": each additional authentication path needs its own policy and tests.
- Do not collapse every `AuthenticationException` into an unmonitored generic infrastructure error: internal logs/telemetry still need safe failure classification.
- This configuration **does not** automatically create a REST JWT login API; it only shows one way to standardize the form-login filter response.

File `src/main/java/example/enumeration/EnumerationDemoApplication.java`:

```java
package example.enumeration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EnumerationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EnumerationDemoApplication.class, args);
    }
}
```

Run with the project's Gradle wrapper:

```bash
./gradlew bootRun
```

When running locally, a sample request **missing a CSRF token** may receive `403` at the CSRF filter **before** reaching username/password verification. Do not mistake that for `DaoAuthenticationProvider` behavior. Use the Spring Security-generated login form to get a valid CSRF token, or write MockMvc tests with `.with(csrf())` as in section 9.

## 9. Testing Spring Security: both absent username and wrong password

Create `src/test/java/example/enumeration/EnumerationFailureTest.java`:

```java
package example.enumeration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@SpringBootTest
@AutoConfigureMockMvc
class EnumerationFailureTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicFailureResponsesAreIdentical() throws Exception {
        MockHttpServletResponse wrongPassword =
            mvc.perform(post("/login").with(csrf())
                    .param("username", "alice")
                    .param("password", "definitely-wrong"))
                .andReturn().getResponse();

        MockHttpServletResponse unknownAccount =
            mvc.perform(post("/login").with(csrf())
                    .param("username", "not-registered")
                    .param("password", "definitely-wrong"))
                .andReturn().getResponse();

        assertEquals(401, wrongPassword.getStatus());
        assertEquals(401, unknownAccount.getStatus());

        assertEquals(
            wrongPassword.getContentAsString(),
            unknownAccount.getContentAsString()
        );
        assertEquals(
            wrongPassword.getContentType(),
            unknownAccount.getContentType()
        );
        assertEquals(
            "{\"error\":\"INVALID_CREDENTIALS\"}",
            wrongPassword.getContentAsString()
        );
    }
}
```

**The import must be on one real line.** In Java, the `import static` above must be written on a single line:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
```

If copying the test file, use this **full import line** instead of the two-line wrapped display. `MockMvc` needs no browser/SMTP, though the test context must locate `EnumerationDemoApplication` and the `SecurityFilterChain` bean.

What this test proves:
- Both failed logins share the **same HTTP status, Content-Type, and JSON body**.
- The test runs through Spring Security filters with valid CSRF, not bypassing filters like direct controller calls.
- `UsernameNotFoundException` is not returned directly to the client.

What it does **not** prove:
- Absence of timing discrepancies over a real network.
- Absence of differences in `Set-Cookie`, other headers, or proxy/CDN paths.
- That password reset, signup, OTT, or mobile API endpoints are also safe.
- That locked/disabled account states return responses identical to the branches above.
- That the codebase implements rate limits, captchas, or cross-service anti-enumeration controls.

### 9.1. Unit testing the provider for both exceptions

You can verify default `DaoAuthenticationProvider` with Java/JUnit when manually configuring a custom provider:

```java
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

// Inside a @Test, with imports and Assertions.assertThrows(...).
var encoder = new BCryptPasswordEncoder();
var service = (org.springframework.security.core.userdetails.UserDetailsService)
    username -> {
        if (!"alice".equals(username)) {
            throw new UsernameNotFoundException("Not found");
        }
        return User.withUsername("alice")
            .password(encoder.encode("secret"))
            .roles("USER").build();
    };

var provider = new DaoAuthenticationProvider(service);
provider.setPasswordEncoder(encoder);

var wrong = UsernamePasswordAuthenticationToken.unauthenticated(
    "alice", "incorrect");
var missing = UsernamePasswordAuthenticationToken.unauthenticated(
    "unknown", "incorrect");

assertThrows(BadCredentialsException.class,
    () -> provider.authenticate(wrong));
assertThrows(BadCredentialsException.class,
    () -> provider.authenticate(missing));
```

`assertThrows` in the snippet is statically imported from `org.junit.jupiter.api.Assertions.assertThrows`. This is an **illustrative code snippet inside a `@Test`**, not a complete Java class. It verifies exception-type masking; **never** use an absolute threshold to claim the method runs in constant time.

## 10. Forgot password: leaks via email and synchronous work

Suppose a controller looks like:

```java
// WRONG: wrong content, wrong status, and timing.
if (accountRepository.existsByEmail(email)) {
    mailService.sendResetEmail(email); // SMTP blocking
    return ResponseEntity.ok("Email sent");
}
return ResponseEntity.status(404).body("Email does not exist");
```

The branch with a user has both different content and a slower SMTP network call. Fixing only the text is not enough if it still does:

```java
// Still has a timing discrepancy if one branch calls SMTP synchronously.
if (accountRepository.existsByEmail(email)) {
    mailService.sendResetEmail(email);
}
return ResponseEntity.ok("If a matching account exists...");
```

### Better architecture: only acknowledge receipt of the request

```text
POST /account/recover
       |
       v
Basic input validation + anti-automation
       |
       v
Enqueue a job into an asynchronous queue
       |
       +--> HTTP 202 + generic message (do not wait for DB/SMTP)
       |
       v
Server-side worker:
  -> look up account
  -> if eligible: issue reset token and send to verified channel
  -> if not eligible: do not issue token
  -> internal logging, audit, rate limiting, and retry handling
```

The HTTP path before responding should look nearly identical whether the account exists or not. Inside the worker, ensure reset tokens are **never** sent to an arbitrary address chosen by the requester for someone else's account.

Example controller contract (Java 17+, Spring MVC); **a real `RecoveryJobQueue` bean must be implemented** with a durable queue—this is a reference architecture, not a standalone email system:

```java
package example.enumeration;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RecoveryController {
    private final RecoveryJobQueue queue;

    public RecoveryController(RecoveryJobQueue queue) {
        this.queue = queue;
    }

    @PostMapping(
        path = "/account/recover",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> recover(
            @RequestParam("email") String email) {

        queue.enqueue(email); // Enqueue the same way, do not look up user here.
        return ResponseEntity.accepted()
            .body("If a matching account exists, instructions will be sent.");
    }
}
```

Queue interface:

```java
package example.enumeration;

public interface RecoveryJobQueue {
    void enqueue(String email);
}
```

**These are two separate Java files** without a `RecoveryJobQueue` implementation yet; provide a real bean and configure retries/TTL/error monitoring before running. If the queue fails or overloads, have a safe, accurate system error policy; never silently claim the request was processed when no job was accepted.

### What makes a reset token valid?

- Generated with a cryptographic random source (`SecureRandom` or equivalent service), sufficient entropy, and unpredictable.
- Bound to the right account and **purpose** of password reset; never reuse login/OTT tokens indiscriminately.
- Short TTL, single-use, atomically consumed.
- Store token verifier/hash safely; avoid keeping raw tokens in logs/databases unless needed.
- Deliver tokens **only** via the real account's verified email/phone channel.
- Rate limit by channel/account/IP and monitor for abuse.
- Never auto-sign-in with full assurance/MFA solely from resetting a password.

### Handling email delivery side channels

You cannot always hide that an email actually reached an account's mailbox, since the legitimate mailbox owner can observe it. The public anti-enumeration goal is that strangers **receive no membership-confirming answer from the endpoint** and receive no secret-bearing email sent to a channel they chose. Security here reduces leakage to **unauthenticated requesters**, rather than pretending no side effects exist anywhere.

## 11. Account registration and checking username availability

Registration always has to check duplicates for uniqueness, yet how to **disclose the result** is a separate security decision.

### Patterns to consider

**Pattern A — Confirmation via email only:** the user submits an email, the server processes asynchronously, and the UI generically says "Please check your inbox if the address is eligible." For already-registered emails, you can send safe instructions to that mailbox or simply send nothing (per policy). Repeated requests by anyone must be throttled.

**Pattern B — Public usernames:** a social network may indicate a username is taken because usernames are public identifiers anyway. Still rate-limit and defend against bulk scraping. This **never** implies disclosing users' emails/phone numbers.

**Pattern C — Only after ownership verification:** detailed status can be confirmed once the requester proves control of the email via a challenge, provided the challenge, TTL, single-use, and scoping are verified.

**Dangerous pattern:** unauthenticated, unthrottled `GET /users/exists?email=...` returning a boolean. Such an API turns the system into a customer-list lookup service.

DB uniqueness must still be enforced by unique constraints and transactions, not only pre-checks in the UI. Avoid returning raw database errors like `DuplicateKeyException: email ... already exists` in JSON/APIs when the goal is hiding membership.

## 12. OTT, OTP, WebAuthn, and MFA: do not reveal the next step too early

Passwordless flows also carry enumeration risks:

### One-Time Token / magic link

If `POST /ott/generate` says "User does not exist" or redirects only existing users to a "mail sent" page, the system leaks account status. Request-acknowledgment responses should be uniform. `OneTimeTokenGenerationSuccessHandler` and the email service must choose a **verified channel** after checking the account, never returning the raw token to the requester. Rate-limit to stop email flooding and abuse.

### TOTP/HOTP

If a user enters a username and the system shows "Enter code from Google Authenticator" **only** for enrolled accounts while showing "OTP not registered" for others, outsiders can guess both account existence and MFA status. Consider showing the factor step only after verifying an appropriate auth step or using a generic prompt by design. Do not weaken MFA just to avoid a slow branch in UX.

### Passkey/WebAuthn

Before authentication, exposing a credential list or "This account has a passkey" can leak membership. Discoverable-credential/usernameless passkey flows help reduce public username queries, though they do not automatically eliminate leaks in fallbacks and recovery.

### Reset MFA / recovery codes

Public endpoints should not announce whether an account has TOTP, passkeys, or issued recovery codes. If a user lacks a factor, follow a recovery policy rather than displaying "You have not enabled MFA" to any request containing an email.

### SSO / identity linking

Home-realm discovery (picking an IdP by email domain) may need to disclose organization domains, yet should not confirm whether an **individual** exists in a tenant. Avoid turning `registrationId`/error URLs or untrusted IdP claims into membership-probing channels. If organization routing requires distinctions, document the threat model and limit disclosure.

## 13. Bearer APIs, OAuth2, GraphQL, and other errors

### Custom login APIs

If `/api/login` calls `UserDetailsService` itself and returns `404` for an unknown user, the framework cannot fix the response automatically. Use `AuthenticationManager.authenticate(...)` and an intentional response normalization layer, never creating an authenticated token before verifying password/token.

### OAuth 2.0 Resource Server

An invalid vs missing token naturally differs by standard OAuth2 error types; account enumeration primarily concerns **token-issuance / account-lookup flows** or custom APIs, not forcing every `401 invalid_token` into one vague response. Resource Servers must follow RFCs/protocols and verify issuer, audience, signature, expiry, and scopes. Never reflect raw detailed exceptions containing emails/account existence into `WWW-Authenticate` or the body.

### GraphQL

GraphQL typically returns HTTP `200 OK` even when resolvers return errors in the payload. If errors return:

```json
{
  "errors": [
    {
      "message": "USER_NOT_FOUND",
      "extensions": {"reason": "UNKNOWN_EMAIL"}
    }
  ]
}
```

membership still leaks. Standardize `errors.message`, `extensions.code`, paths, nullability behavior, and execution steps; not just HTTP status.

### Mobile and legacy clients

Web login may return generic errors while an older mobile app version or Basic endpoint still says "invalid user". Audit **every client/channel** sharing the authentication backend, not just the UI currently under active development. Public test/staging APIs can also leak real account lists if sharing databases.

## 14. Timing mitigation: pick the right fix, avoid blind "sleep"

Principles:

1. **Equivalent essential cryptographic work**: during password auth, for non-existent users, the provider should avoid skipping password-hash verification entirely. Modern `DaoAuthenticationProvider` includes a dummy password hash for the user-not-found branch.
2. **Uniform public responses**: status, content/body, headers, redirects, encoding, and page templates across errors meant to be indistinguishable.
3. **Async side effects**: offload sending email, SMS, and CRM/LDAP enrichment to appropriate workers, rather than having only the known-account branch wait on a network call before responding.
4. **Do not let clients pick sensitive processing branches**: account status, roles, and MFA enrollment must not be disclosed before suitable identity proof.
5. **Align policies across instances**: caches, rate limits, and multi-node backends can create recognizable latency clusters.
6. **Test statistically**: measure many samples in staging, warm up, control network/cache/load, and compare distributions rather than a single request pair.
7. **Keep performance bounded**: do not force heavy multi-round BCrypt on every request in a way that exposes the API to CPU exhaustion.
8. **Protect APIs against automation**: sensible rate limits, quotas, and bot detection to hinder attackers collecting statistical samples.

### Mistake: `Thread.sleep(500)` for non-existent usernames

```java
// Not recommended:
if (user == null) {
    Thread.sleep(500);
    return genericError();
}
```

Because:
- A fixed `sleep` still creates distinct distributions as database/hash/network latencies shift.
- It only patches one branch; email/MFA/other providers still leak.
- It ties up request threads, easily abused for denial of service.
- Attackers can average multiple samples to filter out noise.
- It interacts poorly with deadlines, load, and multi-instance deployments.

A system may consider a **bounded minimum response time or jitter** as defense-in-depth after evaluation, but never as a substitute for equivalent work, throttling, and observability. Bound delays and avoid multiplying unnecessary CPU workload; never advertise strict constant-time HTTP guarantees.

### Mistake: hashing anew on every request to look "heavy"

Do not call `encoder.encode(randomPassword)` repeatedly on every unknown request just to burn time. That wastes CPU and resources and does not necessarily match the work factor of real user passwords. Holding a pre-encoded dummy password is a cleaner approximation for the user-not-found branch, though custom implementations must account for encoding version/cost and rate limiting.

## 15. Pure JDK Java 17: verifying response consistency

This program **does not** verify passwords or call Spring; it demonstrates a unified public mapper. Its goal is deterministic testing with exact stdout. A real system must wire the mapper to its authentication handler and HTTP responses.

File `PublicFailureMappingDemo.java`:

```java
import java.util.List;

public class PublicFailureMappingDemo {

    enum InternalReason {
        USER_NOT_FOUND,
        WRONG_PASSWORD,
        ACCOUNT_LOCKED,
        ACCOUNT_DISABLED
    }

    record PublicReply(int status, String error) {}

    static PublicReply toPublicReply(InternalReason reason) {
        // Internal classification must not enter the public error contract.
        return new PublicReply(401, "INVALID_CREDENTIALS");
    }

    public static void main(String[] args) {
        List<InternalReason> reasons = List.of(
            InternalReason.USER_NOT_FOUND,
            InternalReason.WRONG_PASSWORD,
            InternalReason.ACCOUNT_LOCKED,
            InternalReason.ACCOUNT_DISABLED
        );

        PublicReply baseline = toPublicReply(reasons.get(0));
        boolean identical = true;

        for (InternalReason reason : reasons) {
            PublicReply response = toPublicReply(reason);
            identical &= baseline.equals(response);
            System.out.println(
                reason.name() + ": " + response.status()
                    + " " + response.error()
            );
        }
        System.out.println("public-identical=" + identical);
    }
}
```

Run command:

```bash
javac PublicFailureMappingDemo.java
java PublicFailureMappingDemo
```

**Exact stdout:**

```text
USER_NOT_FOUND: 401 INVALID_CREDENTIALS
WRONG_PASSWORD: 401 INVALID_CREDENTIALS
ACCOUNT_LOCKED: 401 INVALID_CREDENTIALS
ACCOUNT_DISABLED: 401 INVALID_CREDENTIALS
public-identical=true
```

The lesson here is keeping internal error classification separate from the "public contract". This mapper **does not measure timing**, compare headers/cookies, or authenticate. `InternalReason` data must come from a trusted server pipeline; never send this enum to the frontend or put it into redirect URLs where differences leak.

## 16. Testing scenarios from unit to end-to-end

An anti-enumeration test suite checks more than just the body:

### 16.1. HTTP contract tests

| Case pair | What to compare |
| --- | --- |
| Absent username ↔ wrong password | HTTP status, media type, body, redirect |
| Locked/disabled account ↔ wrong password | Identical public login failure contract |
| Registered reset email ↔ unknown email | Identical request-accepted response |
| Enrolled OTP ↔ unenrolled OTP | No status disclosure before suitable proof |
| Existing OTT account ↔ non-existent account | Identical public response and no token returned |
| Duplicate registration email ↔ fresh email | Per disclosure policy; if hidden, compare public responses |
| GraphQL unknown user ↔ wrong credential | `errors.message` and `extensions` do not differ |
| Mobile client v1 ↔ modern web | Equal protection, no legacy enumeration |

Also inspect `Content-Length`, headers, `Set-Cookie`, `Location`, and JSON length/structure. If responses must carry unique `requestId` values, have tests **normalize allowed differing fields** rather than doing fragile raw byte comparisons. Forbid fields such as `userExists`, `matchedAccount`, or `lockedUntil` in public errors.

### 16.2. Safe timing experiments in staging

Run using **team-controlled test accounts**, never probing real user lists:

1. Prepare group A: valid username with wrong password.
2. Group B: non-existent username, same length/format, same password as group A.
3. Group C: locked/disabled test accounts if policy requires checking them.
4. Warm up service, DB pool, JIT, and encoder; keep environment load steady.
5. Send requests at a **limited/permitted rate**, shuffling order randomly to avoid load or cache artifacts.
6. Record server-side and client-side timings separately; compare `p50`, `p90`, `p95` distributions, skew, and tail latency.
7. Test through proxy/load balancer/CDN as well as internal networks, not only direct controller calls.
8. Also test during slow DB, slow mail queue, multi-instance, cold/warm caches, and when rate limits begin triggering.
9. Set acceptable risk thresholds per threat model, then fix the **root cause** of gaps; do not invent a universal millisecond threshold.
10. Ensure tests do not lock real accounts, send bulk emails, or generate uncontrolled load.

**There is no fixed magic threshold** (like "under 5 ms difference is safe"). Adversaries can sample repeatedly over multiple paths; exploitability depends on allowed attempts, gap magnitude, noise, and anti-automation quality.

### 16.3. Testing rate limits and side effects

Verify cases:
- Valid users and unknown users are blocked alike under the right public policy, without leaking membership via `429`.
- Backend queue accepted recovery requests for both cases; mail is delivered only to real accounts, with zero emails sent for strangers.
- Reset tokens have TTL/single-use; no path returns reset tokens in responses.
- When mail/DB fails, logging/monitoring captures it without logging secrets or turning failures into "user exists".
- When an account is locked, responses do not accidentally leak `lockedUntil` or internal metadata.
- Distributed systems keep rate-limiting state and token consumption consistent.

## 17. Rate limiting: essential yet potentially leaky

Rate limiting slows username/password guessing, mail spam, and timing sampling. Yet a system that records counters only for existing accounts can inadvertently create a discrepancy:

```text
Existing account:     after 5 attempts -> 429 TOO_MANY_REQUESTS
Non-existent account: always           -> 401 INVALID_CREDENTIALS
```

A `429` signal like that **is itself an existence probe**.

Better design:
- Combine limits **by IP/network, client/device, hashed/normalized username input, real account when present**, and anti-bot systems; a counter on existing usernames alone is insufficient.
- Count **unknown usernames** in appropriate input-keyed or source-keyed buckets so public policy is hard to distinguish.
- For public APIs, return `429` for general IP-based limits rather than revealing account-specific lockouts; exact details depend on the threat model.
- Use backoff, quotas, and monitoring, avoiding permanent lockouts just because an outsider spams a real user's username (that is DoS).
- If using CAPTCHA, do not show it only for existing accounts; challenge policies should rely on risk signals that do not expose membership.
- Synchronize rate-limit state across the cluster. Test `429` distributions for both existing and non-existent users.

Rate limiting **does not make bodies uniform** and does not eliminate timing side channels, but cuts down the number of probes an attacker can gather. It is an extra layer, not a standalone fix.

## 18. Account status: locked, disabled, expired, and MFA enrollment

`UserDetails` has flags such as `isAccountNonLocked()`, `isEnabled()`, `isAccountNonExpired()`, and `isCredentialsNonExpired()`. Spring Security can throw different exceptions for these states. They are valuable for account control and internal logs, yet returning "account disabled" before proving ownership turns into enumeration.

Considerations:

- To help genuinely locked accounts, send instructions via a **verified channel** after an authorization check process.
- Do not display remaining wrong-attempt counts only for existing accounts if hiding membership.
- Account status checks may run before password verification; **timing** can thus differ from the wrong-password branch. Test locked/disabled states separately.
- Never "fix" a discrepancy by **skipping account status checks** so all users can log in.
- When locked info must be shown to a user who verified an appropriate factor, separate the **verification step** and **display channel** rather than leaking on public login.
- For MFA, never announce passkey/TOTP enrollment merely because the requester knows an email; respond generically until identity proof exists.
- Recovery operations must continue respecting account policies, preventing strangers from using reset flows to enable login on a disabled account.

This is the distinction between **what internals must know about why access was denied** and **how much an unauthenticated caller is entitled to know**.

## 19. Logging, metrics, and investigation without creating new side channels

You need abuse-investigation capability while preserving privacy:

**Metrics to consider:**
- Failure counts per endpoint/source and internal reason group.
- Rates of `401`, `403`, `429`, `5xx` by route, client, and risk level (ensuring no public API exposes reasons).
- Server-side request latency `p50`, `p95`, `p99` across failure flows in controlled environments.
- Volume of reset/OTT requests, queue errors, email delivery errors, retries/backoffs.
- Number of anti-enumeration test runs catching body/status/header/timing differences.
- Account lockout/credential stuffing alerts with anti-DoS rules.

**Do not log:**
- Passwords/OTPs, reset links, raw OTTs, session IDs, JWTs/refresh tokens.
- Full authentication request bodies, especially sensitive payloads.
- Exception stack traces echoed back to responses.
- Emails/phone numbers unnecessary for measurement and investigation.

Send internal events to an access-restricted audit system. If using pseudonymization, note that an unsalted SHA-256 hash of an email can still be reversed via dictionary attacks when input entropy is low; carefully evaluate identity protection.

## 20. Handling UX and product trade-offs

Some products need helpful messages: "Username already taken" on signup, "You don't have an account yet" on support pages. The rule is **not hiding all data at all costs**. Consider:

1. Is system membership sensitive? In healthcare, finance, or HR services, membership can be highly sensitive.
2. Has the requester proven ownership of the email/phone/identity yet?
3. Are usernames publicly visible in the product anyway?
4. Can detailed guidance be moved into **an email sent to the account owner** instead of stating it on the public request?
5. Can real users be helped via generic recovery UIs, verified help desks, or safe informational notices without disclosing accounts to strangers?
6. Do other API/mobile/SSO flows still allow inferring membership?
7. Are rate limiting and abuse monitoring present without turning lockouts into a new oracle?

**A public policy must be consistent**, without breaking protocol-required responses or hiding every operational failure. For instance, a database outage need not impersonate a password error; instead handle it safely, monitor it, and avoid exposing causes tied to a specific account.

## 21. Pre-production checklist

- [ ] Inventoried `/login`, API auth, password reset, registration, OTT/OTP, passkeys, SSO, GraphQL, mobile/legacy, and help desk.
- [ ] No public response contains `USER_NOT_FOUND`, `"unknown email"`, account locked/disabled, or factor status before suitable proof.
- [ ] **Non-existent username** and **wrong password** share consistent status, body, Content-Type, redirects, and headers.
- [ ] `DaoAuthenticationProvider` does not disable `hideUserNotFoundExceptions`; custom providers/handlers follow the same principle.
- [ ] Password verification continues using a suitable `PasswordEncoder`, never plaintext or fast unsalted hashes.
- [ ] User-not-found path does not short-circuit all cryptographic work when using a custom provider.
- [ ] Password reset/OTT requests do not wait on SMTP/SMS only on existing-account branches; delivery uses a monitored queue.
- [ ] Reset/OTT tokens have high entropy, TTL, single-use, go to verified channels, and are never returned in responses.
- [ ] Rate limits cover IP/client/input appropriately, including non-existent usernames; `429` does not reveal account existence.
- [ ] Account lockout cannot become DoS via strangers spamming real usernames.
- [ ] Locked/disabled/expired states do not create easily distinguishable public side channels.
- [ ] Response strings are tested in Vietnamese and other locales.
- [ ] No differing `WWW-Authenticate`, `Location`, `Set-Cookie`, response size, or GraphQL extensions by internal reason.
- [ ] QA timing measured using team-owned test accounts, many samples, warm-up, network/proxy, caches, and cluster.
- [ ] Fixed sleep delays are not used as the sole defense; throttling, metrics, and threat model are in place.
- [ ] Internal logs capture enough reason/code for investigation without unnecessary secrets/PII or leaking reasons to clients.
- [ ] After backend/email/IdP/login flow changes, anti-enumeration regression tests run.
- [ ] A plan exists to support real users without publicly confirming membership.

## 22. Self-check exercises

**Q1.** An API returns `401` for both existing and non-existent users, but a real username takes 120 ms while an unknown username takes 4 ms. Is it safe yet?

**Answer:** Not yet. An exploitable timing discrepancy remains via repeated sampling. Review password verification, DB/service calls, caching, and response paths; use a provider with timing-attack mitigation and measure in staging.

**Q2.** Is setting `setHideUserNotFoundExceptions(true)` sufficient to protect all account recovery flows?

**Answer:** No. That property applies to `AbstractUserDetailsAuthenticationProvider` during authentication; recovery, controllers, email, OTT, and custom APIs require separate policies.

**Q3.** A forgot-password endpoint always returns "Request received", but only waits 300 ms on SMTP when the user exists. What is the problem?

**Answer:** A timing side channel via SMTP. Consider an asynchronous queue and generic response; deliver email only to the verified channel in a subsequent worker.

**Q4.** A username rate-limiting API returns `429` after 5 tries for real accounts, while unknown accounts always get `401`. Does that protect?

**Answer:** It curbs some password-guessing attacks, but creates a new **enumeration oracle**. You need a rate-limiting policy that does not publicly expose membership.

**Q5.** Should "wrong password" errors be hidden by returning `200 OK` and creating a dummy session?

**Answer:** No. Return a generic failure response per contract (e.g., 401/redirect), and **never create an authenticated Authentication or session** when credentials are wrong.

**Q6.** Why might `@ControllerAdvice` not apply to authentication errors in Spring Security form login?

**Answer:** `UsernamePasswordAuthenticationFilter` and `AuthenticationFailureHandler` operate in the filter chain outside MVC controllers. Failure behavior must be configured at the right layer and tested through real filters.

**Q7.** Is reporting "Email already used" during account signup always a mandatory forbidden security bug?

**Answer:** It depends on the threat model and identifier sensitivity. For sensitive membership, avoid it; for public usernames it may be acceptable under policy and rate limits. What matters is an **intentional** decision, not accidentally leaking personal data.

## 23. Summary

Account enumeration is an information-disclosure flaw caused by **observable differences** between existing and non-existent accounts. Differences can appear in messages, HTTP status, URLs, JSON, cookies, headers, SMTP side effects, or response timing.

To reduce risk in Spring Security:

- **Generic messages**, never reflecting internal exceptions to unauthenticated callers.
- **Sound password verification**: use standard `DaoAuthenticationProvider`/`PasswordEncoder`, do not short-circuit user-not-found branches; also check locked/disabled paths.
- **Safe recovery and OTT**: generic replies, asynchronous queues, tokens with entropy/TTL/single-use delivered only to verified channels.
- **Automation controls**: well-designed rate limits/anti-bot controls without special `429` or CAPTCHA behavior only for real accounts.
- **Multi-layer QA**: test HTTP contracts, headers/cookies, JSON format, timing distributions, multi-node, alternate logins, GraphQL/APIs, and logs.
- **Intentional trade-offs**: protect membership while preserving the ability to help verified users and report infrastructure outages.

The goal is not "every request takes exactly 100 ms", but **never accidentally offering a reliable test for others to build an account list**.

## 24. Official references

- OWASP Authentication Cheat Sheet — Authentication responses and discrepancy factors: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Forgot Password Cheat Sheet — consistent responses and timing: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- OWASP Credential Stuffing Prevention Cheat Sheet — reducing automation: https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html
- Spring Security 6.5 — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security Javadoc — `AbstractUserDetailsAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- Spring Security Javadoc — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — CSRF for Servlet applications: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security source — DaoAuthenticationProvider timing mitigation (`SEC-2056`): https://github.com/spring-projects/spring-security/blob/main/core/src/main/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.java
