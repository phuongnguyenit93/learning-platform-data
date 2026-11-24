# oneTimeTokenLogin and Token Issuance and Consumption Endpoints in Spring Security

## 1. Nature of One-Time Token Login (OTT)

In Spring Security, **One-Time Token Login (OTT)** is a sign-in mechanism using a random, short-lived, single-use token, typically sent by email as a **magic link**. The user enters their account name, the application issues a token for that request and delivers it over a verified channel. When the user submits the token back to the login endpoint, the system consumes the token, identifies the account, and establishes a login session if all checks pass.

`HttpSecurity.oneTimeTokenLogin(...)` appeared on the Servlet stack starting in **Spring Security 6.4**. It differs from TOTP/HOTP (codes computed from a shared seed and time/counter), differs from OAuth access tokens (delegated API authorization), and differs from password-reset tokens (used to change passwords). OTT does not automatically replace MFA or post-login authorization checks.

**Core mental model:** there is a **token generation endpoint**, a **token delivery channel**, a **token submission page**, and an **endpoint that actually logs in with the token**. Spring Security handles the filter/service/Authentication parts; the application must actively deliver the token to a trusted address.

### Learning Objectives

- Understand precisely how `POST /ott/generate` differs from `GET /login/ott` and `POST /login/ott`.
- Distinguish `GenerateOneTimeTokenFilter`, `OneTimeTokenGenerationSuccessHandler`, `OneTimeTokenService`, and `OneTimeTokenAuthenticationFilter`.
- Know how to configure a Java 17+/Spring Boot 3.x servlet web app with email magic links and CSRF.
- Know how to customize URLs, expiration, and token storage while avoiding replay, enumeration, host-header poisoning, and race conditions.
- Have criteria to test single-use tokens, expiration, and delivery to the right account.

## 2. End-to-End Flow: Issue → Deliver → View Form → Consume

```text
Browser                        App / Spring Security               Email + OTT Store
  |                                    |                                  |
  | GET /login                         |                                  |
  |----------------------------------->|                                  |
  |<------------ login page -----------|                                  |
  |                                    |                                  |
  | POST /ott/generate                 |                                  |
  | username=alice + CSRF              |                                  |
  |----------------------------------->|                                  |
  |                          GenerateOneTimeTokenFilter                   |
  |                            -> resolve username                        |
  |                            -> OneTimeTokenService.generate() -------->|
  |                            -> success handler sends email ----------->|
  |<------------ 302 /ott/sent --------|                                  |
  |                                    |                                  |
  | Email has /login/ott?token=T       |                                  |
  | GET /login/ott?token=T             |                                  |
  |----------------------------------->|                                  |
  |<------ pre-filled token form ------|                                  |
  |                                    |                                  |
  | POST /login/ott                    |                                  |
  | token=T + CSRF                     |                                  |
  |----------------------------------->|                                  |
  |                        OneTimeTokenAuthenticationFilter               |
  |                          -> AuthenticationProvider                    |
  |                          -> OneTimeTokenService.consume(T) ---------> remove T
  |                          -> UserDetails / Authentication             |
  |                          -> SecurityContext, HTTP session            |
  |<------------ redirect login -------|                                  |
  |                                    |                                  |
  | GET /private + session cookie      |                                  |
  |----------------------------------->|                                  |
  |<------------ Welcome alice --------|                                  |
```

**Specifically:** opening the magic link via **GET** typically only displays the page to confirm/submit the token. GET does not authenticate by itself. In the default Servlet mechanism, the **POST /login/ott** step handles authentication and consumes the token. This helps prevent some email scanners that automatically prefetch GET links from invalidating the token, though it does not guarantee protection against every scanner that interacts more deeply.

## 3. Default Endpoints Table

| Endpoint | Responsibility | Required Data | Handled By |
| --- | --- | --- | --- |
| `GET /login` | Starting page to request OTT (if using default generated page) | Unauthenticated | `DefaultLoginPageGeneratingFilter` |
| **`POST /ott/generate`** | **Issue OTT** | `username`, CSRF if enabled | `GenerateOneTimeTokenFilter` |
| `GET /login/ott?token=T` | Display token submission form, optionally pre-filling T | Query `token` | `DefaultOneTimeTokenSubmitPageGeneratingFilter` |
| **`POST /login/ott`** | **Receive and consume OTT to log in** | Form `token`, CSRF if enabled | `OneTimeTokenAuthenticationFilter` |
| `GET /ott/sent` | Notice that instructions were sent; **application-defined** | None | Application controller/handler |
| `GET /private` | Endpoint requiring an authenticated session | Session cookie after login | SecurityFilterChain + controller |

You may not see `GET /login` if you replace the login page; the two POST endpoints remain the critical ones. **Do not create your own MVC controller handling the same POST /ott/generate or POST /login/ott** while leaving Spring Security filters active on those paths.

### Illustrative Requests

Issuance step:

```http
POST /ott/generate HTTP/1.1
Host: app.example.test
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<session-cookie>

username=alice&_csrf=<csrf-token>
```

The email contains a URL, for example:

```text
https://app.example.test/login/ott?token=<unguessable-token-value>
```

When the browser opens the link, the default form is populated with the token. The user submits:

```http
POST /login/ott HTTP/1.1
Host: app.example.test
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<session-cookie>

token=<unguessable-token-value>&_csrf=<csrf-token>
```

The `<...>` markers above are placeholders, not real tokens. A POST missing a valid CSRF token may return **403 before the OTT filter runs**. Do not conclude that this is an expired-token error, and do not disable CSRF to "fix it".

## 4. Components Inside Spring Security

### 4.1. GenerateOneTimeTokenFilter

The filter intercepts POST issuance requests. It uses `GenerateOneTimeTokenRequestResolver` (which reads `username` by default) to build a `GenerateOneTimeTokenRequest`, calls `OneTimeTokenService.generate(...)`, and passes the resulting `OneTimeToken` to `OneTimeTokenGenerationSuccessHandler`.

The framework **does not automatically know the application's email addresses or SMTP provider**. Registering the OTT DSL without a reliable token delivery mechanism leaves magic link login incomplete.

### 4.2. OneTimeTokenGenerationSuccessHandler

The handler decides what to do once a token exists: look up the **verified email bound to the account**, build the link using a trusted public base URL, send the email/SMS, and return a redirect or neutral notice page. `RedirectOneTimeTokenGenerationSuccessHandler` can help redirect after sending. This is where you must prevent raw token leaks, spam, enumeration, and hostname spoofing.

### 4.3. OneTimeTokenService

The interface provides two core operations:

```java
OneTimeToken generate(GenerateOneTimeTokenRequest request);
OneTimeToken consume(OneTimeTokenAuthenticationToken authenticationToken);
```

These two lines are **conceptual API signature excerpts**; to compile, they must be placed inside an appropriate interface/class with types imported from `org.springframework.security.authentication.ott`. `generate` creates/stores the token and expiration; `consume` must **find, verify, and invalidate the token atomically**. If it returns a valid token to two concurrent requests, the mechanism is no longer "one-time".

`InMemoryOneTimeTokenService` is the default implementation when no other service is declared; suitable for single JVM/demos. `JdbcOneTimeTokenService` uses a database for multiple instances, requiring a patched version and race testing. With a custom token store, consider hashing tokens at rest, TTL cleanup, and limiting pending links.

### 4.4. OneTimeTokenAuthenticationFilter and Provider

`OneTimeTokenAuthenticationFilter` reads the token from **POST /login/ott** and its converter creates an authentication request; `OneTimeTokenAuthenticationProvider` consumes the token and resolves the user. Only on success does Spring create the Authentication/SecurityContext and HTTP session per session policy. OTT does not automatically grant admin rights; account lookup, disabled/locked states, roles, tenant, and business authorization must still be enforced per policy, verifying behavior on your exact version.

### 4.5. DefaultOneTimeTokenSubmitPageGeneratingFilter

This filter renders **GET /login/ott** to display the form and pre-fill the token from the query string. You can replace it with your own HTML page. Whatever UI you use, preserve the **POST loginProcessingUrl**, the `token` form parameter, the CSRF field, and failure handling for invalid/expired/replayed tokens.

## 5. Spring Boot 3.x and Java 17 Example: Magic Link via Email

The example uses **Servlet/Spring MVC** and Spring Security **6.5.10+** (patched for the JDBC OTT bug). The code runs end-to-end only when a test SMTP server, valid public hostname, and test mailbox are configured; no SMTP server exists at the `example.test` domain.

### 5.1. Gradle Dependencies in a Boot Project with the Gradle Plugin Configured

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 5.2. application.yml

File `src/main/resources/application.yml`:

```yaml
app:
  public-base-url: https://app.example.test

spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${SMTP_USER}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
```

Configure `app.public-base-url` from a trusted source, **never taking the request's Host/X-Forwarded-Host** from the browser to construct the link. If Host is attacker-controlled, the magic link can point to a fake domain and leak the token.

### 5.3. OttApplication.java

```java
package com.example.ott;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OttApplication {
    public static void main(String[] args) {
        SpringApplication.run(OttApplication.class, args);
    }
}
```

### 5.4. SecurityConfig.java

```java
package com.example.ott;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, MagicLinkHandler delivery) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/login/ott",
                                "/ott/generate", "/ott/sent")
                        .permitAll()
                        .anyRequest().authenticated())
                // Do NOT disable CSRF; both POST generate and POST login require CSRF.
                .oneTimeTokenLogin(ott -> ott
                        .tokenGenerationSuccessHandler(delivery))
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        // OTT-only demo, formLogin / httpBasic not enabled.
        // Production: real account DB and password encoder if password login is enabled.
        UserDetails alice = User.withUsername("alice")
                .password("{noop}not-used-in-ott")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
```

`permitAll()` on login routes only grants access before authentication; **it does not disable security filters or CSRF**. The `{noop}` password in the demo **is not used to log in** because form login/basic are not enabled; do not use this password storage style for production accounts. When combining OTT with form login, use a strong `PasswordEncoder` and add `formLogin(Customizer.withDefaults())` intentionally.

### 5.5. MagicLinkHandler.java

```java
package com.example.ott;

import java.io.IOException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

@Component
public final class MagicLinkHandler
        implements OneTimeTokenGenerationSuccessHandler {

    private final MailSender sender;
    private final String baseUrl;

    public MagicLinkHandler(MailSender sender,
            @Value("${app.public-base-url}") String baseUrl) {
        this.sender = sender;
        this.baseUrl = baseUrl;
    }

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       OneTimeToken token) throws IOException {
        // Demo only has alice; production looks up verified email from account DB.
        String recipient = "alice".equals(token.getUsername())
                ? "alice@example.test" : null;

        if (recipient != null) {
            String link = UriComponentsBuilder.fromUriString(baseUrl)
                    .path("/login/ott")
                    .queryParam("token", token.getTokenValue())
                    .build().encode().toUriString();

            SimpleMailMessage mail = new SimpleMailMessage();
            mail.setTo(recipient);
            mail.setSubject("Your one-time sign-in link");
            mail.setText("Use this link to sign in: " + link);
            this.sender.send(mail);
        }
        response.sendRedirect(request.getContextPath() + "/ott/sent");
    }
}
```

The email `alice@example.test` is a placeholder that receives no mail. Replace it with a test inbox when running. If the username is unknown, the example sends nothing and still redirects to the common page. Real products need verified email lookup, rate limiting, anti-account-enumeration, queue retries, and SMTP error handling that does not reveal whether the account exists. Never use a `recipientEmail` entered by the requester as the delivery address for another account's link. SMTP errors can throw exceptions; this snippet does not yet implement error masking/retries, so use it only as an integration lesson.

### 5.6. PageController.java

```java
package com.example.ott;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PageController {
    @GetMapping("/")
    public String index() {
        return "OTT demo";
    }

    @GetMapping("/ott/sent")
    public String sent() {
        return "If the account is eligible, check its email.";
    }

    @GetMapping("/private")
    public String privatePage(Principal principal) {
        return "Welcome " + principal.getName();
    }
}
```

### 5.7. Running

In a project with the Gradle wrapper:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

Open `/login`, submit the POST `/ott/generate` form with `username=alice` and CSRF. The system should deliver the magic link to the right email; open `GET /login/ott?token=T` and submit **POST /login/ott** with token+CSRF. On success, `GET /private` with the session cookie returns `Welcome alice`. Another browser without the cookie remains unauthenticated. Do not pass raw tokens through shell history or logs.

## 6. Customizing Endpoints and Expiration

| Item | Default | How to Change |
| --- | --- | --- |
| Generation endpoint | `POST /ott/generate` | DSL for generating URL |
| Token processing endpoint | `POST /login/ott` | `loginProcessingUrl(String)` |
| Default token receive page | `GET /login/ott` | DSL for default submit-page URL; `showDefaultSubmitPage(false)` for custom UI |
| Token delivery | Custom application | `tokenGenerationSuccessHandler(...)` |
| Token storage | `InMemoryOneTimeTokenService` default | `tokenService(...)` or `OneTimeTokenService` bean |
| Parse username and expiresIn | Default request resolver | `generateRequestResolver(...)` / custom resolver |

**Method names vary between documentation and artifact versions:** some Spring Security Javadocs use `tokenGeneratingUrl(...)` and `defaultSubmitPageUrl(...)`, while examples in some documentation branches use `generateTokenUrl(...)` and `submitPageUrl(...)`. Always check the **Javadoc of the Spring Security version your project actually uses** before copying setters. The sample in section 5 keeps the default URLs and the stable success handler API.

If changing URLs, update **the issuance form action**, **the GET magic link**, **the login POST form action**, permitAll routes, and the reverse proxy. The GET page and POST processor do not have to share the same URL. If using `showDefaultSubmitPage(false)`, you must render the GET page/form yourself, while the POST filter still needs configuration.

Example resolver to set a 10-minute TTL (snippet inside Java configuration, not a standalone file):

```java
var resolver = new DefaultGenerateOneTimeTokenRequestResolver();
resolver.setExpiresIn(java.time.Duration.ofMinutes(10));
// ott.generateRequestResolver(resolver) on versions that have this method.
```

Import from `org.springframework.security.web.authentication.ott.DefaultGenerateOneTimeTokenRequestResolver`. The default lifetime is about 5 minutes in 6.5 releases, though you should confirm in the configuration of your running version. Longer TTLs widen the link-exposure window, so balance against email latency.

## 7. Token Storage, Concurrency, and the CVE-2026-22751 Patch

### 7.1. In-Memory for Demos/Single Instance

Without a custom bean, `InMemoryOneTimeTokenService` keeps tokens in JVM memory, convenient for demos and tests. Restarts lose pending tokens; multiple pods do not share state. A generation request hitting instance A and a login POST hitting instance B can fail without a shared store.

### 7.2. JDBC for Multi-Node Systems

`JdbcOneTimeTokenService` stores OTTs in a database for multiple instances, but **consume must be atomic**. A flawed implementation can let two concurrent requests both see an unused token and open two sessions. Spring disclosed **CVE-2026-22751** on **2026-04-21** specifically affecting explicitly configured `JdbcOneTimeTokenService`:

- Affected: **Spring Security 6.4.0–6.4.15**, **6.5.0–6.5.9**, **7.0.0–7.0.4**.
- Fixed versions: **6.5.10** and **7.0.5** in OSS branches; **6.4.16** via Enterprise Support.
- Default `InMemoryOneTimeTokenService` **is not affected by this specific CVE**.

If your application uses `JdbcOneTimeTokenService`, verify that your runtime dependency BOM resolves a patched version and test **two concurrent POSTs with the same token on two separate sessions**. For custom stores, never perform a separate SELECT followed by DELETE without proper locking/atomic update:

```sql
-- Illustrative race-prone logic, NOT safe without proper transaction/locking:
SELECT username, expires_at FROM ott_tokens WHERE token_hash = ?;
-- Concurrently, two requests may both see the token as valid.
DELETE FROM ott_tokens WHERE token_hash = ?;
```

Use an atomic update/delete + affected-rows check within a transaction on a supporting DB; exact SQL syntax depends on the real DB and schema. Never claim "deleting one row" is enough if another request could read it before deletion.

### 7.3. Tokens Must Be Confidential and Short-Lived

Require high entropy, short TTL, single-use, hashed tokens at rest (in custom designs), expired-token cleanup, per-account pending-token quotas, and token invalidation on email change/account lock per policy. Do not log raw tokens in logs/metrics/tracing or resend already-consumed tokens.

## 8. Plain Java 17: Demonstrating Atomic Single-Use

File `SingleUseTokenDemo.java` below runs standalone with JDK 17+. It shows why an atomic remove operation matters, though it **does not** implement Spring's `OneTimeTokenService`, does not send mail, and does not prove a distributed database has the right semantics.

```java
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class SingleUseTokenDemo {
    record Entry(String username, Instant expiresAt) {}

    private static final SecureRandom RANDOM = new SecureRandom();
    private final ConcurrentHashMap<String, Entry> tokens =
            new ConcurrentHashMap<>();

    String generate(String username, Instant now) {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        String value = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(bytes);
        tokens.put(value, new Entry(username,
                now.plus(Duration.ofMinutes(5))));
        return value;
    }

    boolean consume(String value, Instant now) {
        Entry entry = tokens.remove(value); // atomic within one JVM
        return entry != null && now.isBefore(entry.expiresAt());
    }

    public static void main(String[] args) throws InterruptedException {
        SingleUseTokenDemo demo = new SingleUseTokenDemo();
        Instant now = Instant.parse("2026-11-06T00:00:00Z");

        String token = demo.generate("alice", now);
        System.out.println("first=" + demo.consume(token, now));
        System.out.println("replay=" + demo.consume(token, now));

        String expired = demo.generate("alice", now);
        System.out.println("expired=" +
                demo.consume(expired, now.plus(Duration.ofMinutes(6))));

        String shared = demo.generate("alice", now);
        CountDownLatch gate = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger accepted = new AtomicInteger();

        Runnable attempt = () -> {
            try {
                gate.await();
                if (demo.consume(shared, now)) {
                    accepted.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        };
        new Thread(attempt).start();
        new Thread(attempt).start();
        gate.countDown();
        done.await();

        System.out.println("concurrentSuccess=" + accepted.get());
    }
}
```

Run:

```bash
javac SingleUseTokenDemo.java
java SingleUseTokenDemo
```

Deterministic stdout:

```text
first=true
replay=false
expired=false
concurrentSuccess=1
```

When calling `remove` on a `ConcurrentHashMap`, only one thread retrieves the entry. With a database, dedicated locking/atomic consume is required; this example intentionally omits HTTP/JWT/Spring logic so the one-time condition is clear.

## 9. Security Essentials That Must Not Be Skipped

**CSRF:** Both POST requests in the OTT flow require valid CSRF in a browser session. `.permitAll()` does not bypass CSRF. A 403 from a missing `_csrf` differs from an expired token. When writing a custom login form, render/submit the CSRF token properly.

**A magic link is a bearer secret:** whoever holds the link can log in first. Query tokens can leak into browser history, logs, reverse proxies, Referer/analytics, and third-party scripts. Use HTTPS, `Referrer-Policy: no-referrer`, exclude tracking JS from token-bearing submit pages, and consider stripping the query parameter from the URL after the form captures the token. Do not switch to "direct GET authentication" because of scanner prefetching.

**Trusted email address:** do not send a magic link to an `email` entered by the requester for another username. Look up verified email in the account DB; prevent attackers from entering a victim's username and receiving the link at the attacker's email. Never build URLs from an unverified Host.

**Anti-spam/enumeration:** public issuance endpoints are easy spam targets. Rate limit by IP/user, enforce quotas, keep notices neutral, keep timing/responses consistent, monitor abuse, and protect the SMTP queue. If an account does not exist or is locked, do not return a visibly different error that leaks information; account state must also be checked at login.

**Post-OTT session:** a consumed token cannot be reused, but the HTTP session created by login persists via cookie. Protect against session fixation, configure Secure/HttpOnly/SameSite, handle logout, timeouts, and MFA/step-up for high-risk actions. Do not treat email possession as sufficient for admin privileges.

**Concurrency:** one token must yield at most one login, even across two concurrent requests on two nodes. Testing against real JDBC matters more than a test that only mocks `Authentication`.

## 10. Test Matrix for Issuance and Consumption

| Case | Action | Expected |
| --- | --- | --- |
| Request page | `GET /login` | Displays OTT form or custom login page |
| Wrong generate method | `GET /ott/generate?username=alice` | No token issued |
| Generate missing CSRF | POST username without `_csrf` | 403, no email |
| Valid generate | POST username + CSRF | Creates token, handler sends to verified email |
| Non-existent user | POST unknown username | Does not send token to attacker's email, neutral response |
| Click link | `GET /login/ott?token=T` | Only renders form, not logged in, not consumed |
| Login missing CSRF | POST token T, no CSRF | 403; not authenticated |
| Valid login | POST T+CSRF before expiry | Consumes T, right user authenticated |
| Replay | POST T a second time in another browser | Rejected |
| Expired | POST past TTL | Rejected |
| Concurrent requests | Two POSTs with same token from two sessions/DB nodes | Exactly one succeeds |
| Locked account | Valid token but account disabled | Rejected per account policy |
| Multi-instance | Generate pod A, consume pod B | Passes if token store is properly shared |
| Host injection | Generate with spoofed Host | Link still uses configured public base URL |
| Mail scanner | Prefetch GET magic link | Token is not yet consumed |

Use `spring-security-test` to test CSRF in `MockMvc`:

```java
// Snippet inside a @SpringBootTest + @AutoConfigureMockMvc test
// with MockMvc mvc and static imports post, status, csrf:
mvc.perform(post("/ott/generate")
        .param("username", "alice"))
   .andExpect(status().isForbidden());

// When a mock MailSender is configured:
// mvc.perform(post("/ott/generate")
//        .with(csrf())
//        .param("username", "alice"))
//    .andExpect(status().is3xxRedirection());
```

This is a **fragment**, not a standalone runnable test class. Real OTT verification must assert that the token was sent to the right account, POST consumption creates a session, replay fails, and concurrent use of the same token allows only one login. Tests using `@WithMockUser` to synthesize a principal upfront **do not prove the OTT filter works**.

## 11. Quick Troubleshooting

| Symptom | Common Cause | How to Verify |
| --- | --- | --- |
| POST generate 403 | Missing CSRF / cookie mismatch | Inspect CSRF filter, hidden form input, and session |
| GET generate issues no token | Only POST is handled by the filter | Use POST /ott/generate |
| POST succeeds but no email | Missing success handler/SMTP or wrong email mapping | Check bean, queue, verified email |
| GET link opens but not logged in | It is only the submit page | User must POST /login/ott |
| POST login invalid token | Expired/used/lost store/JVM restart | Check store + TTL + instance |
| Token reused in concurrent requests | Unpatched JDBC or non-atomic custom store | Upgrade, test two concurrent POSTs |
| Multi-pod intermittent failures | Unshared InMemory store | JDBC/shared store |
| Locked account still logs in | Account state not enforced | Test disabled/locked with exact provider version |
| Link has wrong domain | Using untrusted Host/X-Forwarded-Host | Configure fixed public base URL |
| Session lost after login | Wrong Secure/SameSite/domain/cluster cookie | Network Set-Cookie and persistence |
| Email scanner auto-consumes | Custom GET handler logs in | GET only renders form, POST consumes |
| Token appears in logs | Access log/analytics/referrer captures query | Mask token, Referrer-Policy, remove scripts |

## 12. Closing Checklist

- **POST /ott/generate** issues, **GET /login/ott** only shows the form, and **POST /login/ott** accepts/consumes and signs in.
- Configured `oneTimeTokenLogin(...)` and `OneTimeTokenGenerationSuccessHandler` to send tokens to DB-verified addresses without returning the token to the caller.
- Have CSRF, HTTPS, a trusted public base URL, rate limiting, anti-enumeration, and keep tokens out of logs/referrers.
- Short TTL, high-entropy random tokens, **atomic single-use**, tested against replay and concurrent requests.
- Topology-appropriate store: InMemory only for single JVM/demos; JDBC/shared stores need the **CVE-2026-22751** patch and multi-instance testing.
- Successful login attaches the right user/authorities and session; locked/disabled accounts and business permissions are checked separately.
- When changing DSL URLs, consult Javadoc for the exact version and update both the GET magic link and the POST form.

**Short summary:** `oneTimeTokenLogin()` integrates single-use token generation and consumption, but the application must build the **delivery path to the account owner**. Opening the magic link via GET is not the authentication step; only a valid POST can sign in.

### Official Learning Resources

- [Spring Security 6.5 Reference — One-Time Token Login (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html)
- [Spring Security Reference — One-Time Token Login](https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html)
- [Spring Security 6.5 Javadoc — OneTimeTokenLoginConfigurer](https://docs.spring.io/spring-security/site/docs/6.5.5/api/org/springframework/security/config/annotation/web/configurers/ott/OneTimeTokenLoginConfigurer.html)
- [OneTimeTokenService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ott/OneTimeTokenService.html)
- [Spring Security Advisory — CVE-2026-22751, JDBC concurrent consumption](https://spring.io/security/cve-2026-22751/)
