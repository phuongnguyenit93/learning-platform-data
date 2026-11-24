# When to Consider Exceptions and Why Not to Disable CSRF Out of Habit

> **Module:** Spring Security - fundamentals  
> **Parent topic:** CSRF  
> **Principle:** Never disable CSRF simply because a `POST` request returns `403 Forbidden`. First determine whether the browser automatically sends credentials. If an exemption is genuinely needed, scope the exception to the **exact endpoint, HTTP method, and authentication model**, then verify remaining endpoints stay protected.

## 1. Learning Objectives

After this lesson, you can:

- Explain **Cross-Site Request Forgery (CSRF)** and why session cookies let unintended actions be sent under a logged-in user's identity.
- Distinguish CSRF from **authentication**, **authorization**, CORS, and XSS; understand why `permitAll()` does not exempt requests from CSRF.
- Know when there is valid ground to **consider an exception**, such as a server-to-server webhook with verified signatures, or an API accepting only Bearer tokens in headers with no browser auto-sent credentials.
- Use Spring Security 6 with `csrf.ignoringRequestMatchers(...)` to exempt **a specific route and method**, instead of `csrf.disable()` across the whole application.
- Understand practical Spring Security details: HTTP safe methods, `CsrfFilter`, `CsrfTokenRepository`, tokens in forms/headers, login/logout, SPAs, and token rotation.
- Build a Spring Boot/Java 17 example with a browser endpoint requiring CSRF and a webhook endpoint exempt from CSRF tokens yet protected by an **HMAC signature**.
- Write tests verifying both **allowed** and **rejected** branches to ensure exemptions do not accidentally expose unauthorized paths.

## 2. What Bug Is CSRF?

Suppose Alice logs into a banking application that maintains sessions with cookies. Alice's browser stores the session cookie; when the browser sends requests to the bank within cookie scope, the cookie can be attached automatically.

While still logged in, Alice opens a page controlled by an attacker. That page tries making the browser send a state-changing request to the bank:

~~~text
Alice logged into bank
         |
         | Browser holds bank's session cookie
         v
Opens attacker's page
         |
         | HTML form or other request targeting bank
         v
Browser sends request to bank
         |
         | Cookie auto-sent by browser per cookie rules
         v
Bank sees Alice's session
         |
         v
Without anti-CSRF defense, action may be processed
~~~

Malicious form example illustrating the concept:

~~~html
<form action="https://bank.example.invalid/transfer" method="post">
  <input name="recipient" value="attacker-account">
  <input name="amount" value="100">
  <button type="submit">Click to view photo</button>
</form>
~~~

This is a **threat-illustration example**, not a real bank URL. The attacker does not necessarily need to read the response. If the request carries valid browser-attached credentials and the server verifies only "Alice is logged in" without checking Alice's active intent for the operation, the server may execute the unwanted action.

**Valid authentication does not equal valid user-intended requests.** Precisely because browsers support cookies, HTTP Basic, or other auto-sent credentials, the server needs an extra signal that an attacker's page cannot fabricate.

## 3. Defense Mechanism: Synchronizer CSRF Token

Spring Security applies CSRF protection to operations requiring defense. Synchronizer token model:

1. The server generates an unpredictable random token, binding it to the user's appropriate context, such as `HttpSession`.
2. Legitimate pages or JavaScript clients receive the token via a channel external pages cannot arbitrarily forge or read under the same conditions.
3. When sending a state-changing request, the client submits the token in a **form parameter** or **HTTP header**.
4. The server compares the received token with the expected token. Missing/wrong token → request rejected.

~~~text
SAME SESSION COOKIE

Request A:
  Cookie: JSESSIONID=...
  Header/form: _csrf=<correct-token>
    => Passes CSRF check (must still check permissions)

Request B:
  Cookie: JSESSIONID=...
  Missing CSRF token or wrong token
    => Rejected before running business logic
~~~

**Important:** If a system requires only "the CSRF token is present in a cookie", that requirement helps nothing because browsers also auto-send cookies in some cross-site scenarios. The **client must place the token value in a parameter/header** following rules an attacker's page cannot arbitrarily supply.

### What Does Spring Security Servlet Handle?

- `CsrfFilter` determines whether a request needs a CSRF check and compares tokens.
- `CsrfTokenRepository` stores/loads expected tokens. Default Servlet setup normally uses `HttpSessionCsrfTokenRepository`.
- `CsrfTokenRequestHandler` exposes the token to requests and resolves tokens from headers/form parameters.
- `XorCsrfTokenRequestAttributeHandler` is the default handler in Spring Security 6, supporting BREACH protection via masked token representations.
- When a token is missing or invalid, requests may be rejected with `MissingCsrfTokenException` or `InvalidCsrfTokenException`, typically yielding a `403` response.

Do not assume every HTTP `403` is caused by CSRF. It can also come from authorization rules, method security, or a custom handler. Identify the rejecting layer before changing configuration.

## 4. Which HTTP Methods Need CSRF?

By default, Spring Security skips CSRF checks for **safe methods**:

- `GET`
- `HEAD`
- `OPTIONS`
- `TRACE`

And by default checks other methods, including `POST`, `PUT`, `PATCH`, and `DELETE`.

| Request | Needs CSRF token by default? | Underlying assumption |
| --- | --- | --- |
| `GET /products` | No | GET must produce zero business side effects |
| `HEAD /products` | No | Read-only, does not mutate state |
| `OPTIONS /products` | No | Probes endpoint capabilities, writes no data |
| `POST /transfer` | Yes | Browser uses cookie/session |
| `PUT /account/profile` | Yes | Can modify info |
| `PATCH /account/settings` | Yes | Can modify settings |
| `DELETE /account/saved-card` | Yes | Can delete data |

**Never put write operations on GET and claim it is safe because Spring does not require CSRF for GET.** CSRF configuration relies on safe methods truly being read-only. For example, `GET /delete-account?id=42` violates HTTP semantics and breaks the security premise.

### Login and Logout Are Also State-Changing Operations

A login form changes authentication state and may create a new session. A logout request invalidates a session. Spring Security supports CSRF on `POST /login` and `POST /logout` when CSRF is enabled; `GET /logout` can display a confirmation page to submit a POST with a CSRF token.

Never disable CSRF "so the logout button stops getting 403" or arbitrarily convert logout to GET. Fix the form to send the token properly.

## 5. Why Should You Not Disable CSRF Out of Habit?

The following is a **broad** change:

~~~java
// CAUTION: disables CSRF checks for the ENTIRE SecurityFilterChain.
http.csrf(csrf -> csrf.disable());
~~~

It allows tokenless `POST` requests to proceed. If the app uses cookies/sessions or other browser auto-sent credentials, a critical protection layer has been removed.

Statements that "sound plausible yet are wrong":

| Argument | Problem |
| --- | --- |
| "API returns JSON so CSRF isn't needed" | JSON responses do not decide whether browsers auto-send credentials |
| "Using `@RestController` means no CSRF" | `@RestController` can still accept session cookies or HTTP Basic |
| "Authentication is present, strangers can't log in" | CSRF borrows the already logged-in user's own browser |
| "Role checks exist so it's safe" | Forged requests can carry the victim's real roles |
| "CORS is enabled so that's enough" | CORS mainly governs response reading/certain cross-origin calls, not replacing CSRF tokens for forms |
| "SameSite is set so it's definitely safe" | SameSite is a supplemental layer with site, browser, and integration limits |
| "Using HTTPS prevents CSRF" | HTTPS protects transport, not confirming user intent |
| "POST tests getting 403 is inconvenient" | Fix tests to send CSRF tokens or define evaluated exemptions |
| "Just use `permitAll()`" | Endpoint access rights and CSRF are independent checks |
| "Stateless API so always disable CSRF" | Stateless is insufficient if browsers still auto-send valid credentials like HTTP Basic or cookies |

**The decisive question is not "Is it REST?" but "Can a malicious page make a browser send an authenticated request without knowing the credential?"**

## 6. When Can an Exception Be Considered?

There is no rule saying "if an endpoint is a webhook/API, disable CSRF". Analyze **request origin, credentials, browser behavior, and alternate verification**.

### 6.1. Server-to-Server Webhooks with Strong Authentication

A payment provider sends `POST /webhooks/provider` directly from their server. The request does not originate from a browser logged in with session cookies; the client has no user CSRF token.

In this model, it can be reasonable to **exempt that exact POST endpoint from CSRF** and replace it with proper verification such as an HMAC signature over the raw payload, timestamp/replay protection, idempotency, rate limiting, and provider event checks.

~~~text
Provider Server
    |
    | POST /webhooks/provider
    | X-Webhook-Signature: sha256=...
    v
Spring Boot
    |
    +-- Exempt CSRF specifically for POST /webhooks/provider
    |
    +-- VERIFY provider signature and replay policy
            |
            +-- invalid -> DENY
            +-- valid -> process per policy
~~~

**Exempting CSRF does not mean dropping authentication/authorization.** Because CSRF does not solve server-to-server authentication, webhooks need dedicated verification. Never treat a static header like `X-Webhook: true` as trustworthy authentication.

### 6.2. Machine-to-Machine APIs Accepting Only Bearer Tokens in HTTP Authorization Headers

A resource server accepting solely:

~~~http
POST /machine/jobs HTTP/1.1
Host: api.example.invalid
Authorization: Bearer <access-token>
Content-Type: application/json

{"name":"job1"}
~~~

If the endpoint **genuinely does not** accept session cookies, Basic authentication, or auto-sent credential mechanisms, and clients actively attach Bearer tokens in headers, a foreign page's browser neither knows the token nor auto-sends it like cookies.

Then omitting CSRF tokens may be considered for **the specific security chain serving machine clients**. Still verify:

- Does that chain truly accept only Bearer tokens?
- Is session creation disabled appropriately?
- Are there any cookie-based fallbacks, proxy auto-auth, client certificates, HTTP Basic, or web endpoints sharing the chain?
- Does CORS policy block untrusted sites where needed?
- Does the access token enforce proper issuer, audience, expiry, scopes, and policies?

**JWT tokens stored in cookies still carry CSRF risk**, because browsers send cookies automatically. Never deduce "JWT" = "no CSRF".

### 6.3. Native Mobile/CLI Clients Not Using Browser Cookies

An API serving exclusively native mobile or CLI apps where clients attach credentials to headers manually may not need synchronizer CSRF tokens. However, if **the same backend** also receives browser cookie traffic, never disable CSRF across the entire backend simply because one mobile client calls POST.

Design a separate auth path, separate chain, or browser CSRF token retrieval to preserve each trust boundary.

### 6.4. Internal Event Endpoints with Independent Authentication

Internal scheduler callbacks, message-delivery callbacks, or health agents **not relying on browser credentials** can be evaluated for method/path exemptions if they enforce dedicated authentication (mTLS, signatures, OAuth2 client credentials, plus network restrictions as a supporting layer).

Merely calling an endpoint "internal" or "headless" is not enough. If a browser can invoke it with user cookies or an internal network is reachable from an untrusted origin, re-evaluate the risk.

## 7. Decision Guide: Which Requests to Protect, Which to Exempt?

| Request type | Credentials and environment | Initial recommendation |
| --- | --- | --- |
| Web MVC/Thymeleaf form POST | Session cookie | **Keep CSRF** |
| SPA sending session cookie | Auto-attached cookie | **Keep CSRF**, integrate token via header |
| REST API using session cookie | Auto-attached cookie | **Keep CSRF** even with JSON body |
| REST API with JWT in cookie | Auto-attached cookie | **Keep CSRF** or design verified equivalent protection |
| API with Bearer token solely in `Authorization` header | No auto-sent credentials | Can consider exemption if chain/endpoint is truly stateless |
| Webhook from partner server | Server-to-server HMAC/mTLS/token, no user cookies | Can exempt exact method/path and verify signature |
| HTTP Basic API for browsers | Browser may auto-send credentials | **Do not auto-exempt CSRF** |
| `permitAll()` URL that mutates state | May have auto-sent cookies/credentials | **Do not auto-exempt CSRF** |
| CORS preflight `OPTIONS` | Safe method | No CSRF token needed by default; configure CORS separately |
| Side-effecting GET | Broken HTTP semantics | Refactor API to unsafe method and protect properly |

**When uncertain about credential delivery**, default to keeping CSRF and investigate. Exemptions are responsible design decisions, not quick shortcuts to make tests "green".

## 8. Narrowly Scoped Exceptions: `ignoringRequestMatchers`

In Spring Security 6 Servlet, you can configure:

~~~java
// Illustrative snippet only inside SecurityFilterChain.
http.csrf(csrf -> csrf
    .ignoringRequestMatchers(
        new AntPathRequestMatcher("/webhooks/provider", "POST")
    )
);
~~~

Thus **only** `POST /webhooks/provider` is exempted from CSRF by this matcher; other POST routes still require tokens. `AntPathRequestMatcher` exists in this example's Spring Security 6.x; newer versions may prefer different matcher APIs, so check documentation for your actual version.

Do not write:

~~~java
// TOO BROAD if /api/** includes browser/session endpoints.
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/api/**")
);
~~~

without proof that every route under `/api/**` avoids browser auto-credentials. The broader the URL pattern, the easier it becomes to accidentally exempt new endpoints added by someone later.

### `permitAll` Differs from `CSRF ignore`

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/webhooks/provider").permitAll()
)
.csrf(csrf -> csrf
    .ignoringRequestMatchers(
        new AntPathRequestMatcher("/webhooks/provider", "POST")
    )
)
~~~

- `permitAll` states the request **does not need a logged-in principal** at Spring Security's authorization layer.
- `ignoringRequestMatchers` states the request **does not need a CSRF token**.
- Neither **automatically provides** webhook signature verification. A valid HMAC/mTLS/OAuth2 policy is still required separately.

Conversely, a public `/register` URL with `permitAll` accepting POSTs from browsers can still need CSRF to prevent forged submissions.

## 9. Runnable Java 17 Example: Keep CSRF for Browsers, Exempt Signed POST Webhooks

The example below uses:

- Java 17+.
- Spring Boot 3.3.5 / Spring Security 6.x.
- Gradle 8.x.
- A `POST /settings` endpoint protected by authentication **and CSRF**.
- A `POST /webhooks/vendor` endpoint exempted **specifically** from CSRF yet verifying an HMAC SHA-256 signature over the raw request body.
- MockMvc tests verifying requests missing tokens are denied, valid tokens are accepted, and the webhook exemption works only with a valid signature.

**Learning scope:** HMAC in the example checks basic payload authenticity/integrity. Production webhooks must follow the **exact provider signing spec**, adding timestamps/replay windows, idempotency, secret rotation, and error handling. A valid signature can still be replayed without anti-replay checks.

### 9.1. Project Structure

~~~text
csrf-exception-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/csrf/
    │   ├── CsrfDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── SettingsController.java
    │   ├── WebhookVerifier.java
    │   └── WebhookController.java
    ├── main/resources/
    │   └── application.properties
    └── test/java/demo/csrf/
        └── CsrfPolicyTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'csrf-exception-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 9.2. Starting the Application

File `src/main/java/demo/csrf/CsrfDemoApplication.java`:

~~~java
package demo.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }
}
~~~

### 9.3. SecurityFilterChain: Protect by Default, Exempt Only Webhook POST

File `src/main/java/demo/csrf/SecurityConfig.java`:

~~~java
package demo.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers(
                    HttpMethod.POST, "/webhooks/vendor"
                ).permitAll()
                .anyRequest().authenticated()
            )
            // CSRF stays ENABLED on all other requests.
            .csrf(csrf -> csrf.ignoringRequestMatchers(
                new AntPathRequestMatcher("/webhooks/vendor", "POST")
            ))
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }
}
~~~

**Key point:** There is no `csrf.disable()`. Default CSRF protection remains intact. The matcher specifies method `POST` and an exact path, not every URL starting with `/webhooks/`.

`formLogin` is kept so the example has a web-style authenticated flow. In tests, `@WithMockUser` supplies a principal to focus on CSRF checks without performing UI login steps.

### 9.4. Side-Effecting Endpoint Protected by CSRF

File `src/main/java/demo/csrf/SettingsController.java`:

~~~java
package demo.csrf;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SettingsController {

    private final AtomicInteger updates = new AtomicInteger();

    @GetMapping("/health")
    public String health() {
        return "ok";
    }

    @PostMapping("/settings")
    public String update() {
        updates.incrementAndGet();
        return "updated";
    }

    public int updateCount() {
        return updates.get();
    }

    public void resetForTest() {
        updates.set(0);
    }
}
~~~

`AtomicInteger` is sample state, not a database. We will test that requests with missing/invalid CSRF tokens **never enter the body of `update()`**; it does not increment. When an authenticated request carries a valid token, the method runs and the count increments.

### 9.5. Signature Verification for Webhooks

File `src/main/java/demo/csrf/WebhookVerifier.java`:

~~~java
package demo.csrf;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class WebhookVerifier {

    private final byte[] key;

    public WebhookVerifier(@Value("${demo.webhook.secret}") String secret) {
        this.key = secret.getBytes(StandardCharsets.UTF_8);
    }

    public boolean isValid(byte[] payload, String signatureHeader) {
        if (signatureHeader == null
                || !signatureHeader.startsWith("sha256=")) {
            return false;
        }

        String hex = signatureHeader.substring("sha256=".length());
        if (!hex.matches("[0-9a-fA-F]{64}")) {
            return false;
        }

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));

            byte[] expected = mac.doFinal(payload);
            byte[] provided = HexFormat.of().parseHex(hex);

            return MessageDigest.isEqual(expected, provided);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("HMAC is unavailable", e);
        }
    }
}
~~~

Notable points:

- HMAC is computed over **raw request bytes**; do not deserialize JSON and re-serialize before verifying, as that can alter the canonical payload.
- `MessageDigest.isEqual` compares bytes to avoid naive sequential comparisons prone to timing leaks.
- The code validates signature format before parsing, rejecting malformed headers.
- Never place production secrets as literals in source code; the example uses a local test secret, while production needs environment variables/secret managers.
- Sample code **does not yet** block replays. You must add timestamps, time windows, event IDs/idempotency, and the provider's exact signing rules before handling real transactions.

File `src/main/java/demo/csrf/WebhookController.java`:

~~~java
package demo.csrf;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WebhookController {

    private final WebhookVerifier verifier;

    public WebhookController(WebhookVerifier verifier) {
        this.verifier = verifier;
    }

    @PostMapping("/webhooks/vendor")
    public ResponseEntity<String> receive(
            @RequestBody byte[] payload,
            @RequestHeader(
                value = "X-Webhook-Signature", required = false
            ) String signature) {
        if (!verifier.isValid(payload, signature)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body("invalid signature");
        }

        return ResponseEntity.accepted().body("accepted");
    }
}
~~~

Application config for **local demo**:

File `src/main/resources/application.properties`:

~~~properties
server.port=8080
demo.webhook.secret=local-demo-secret-change-before-production
~~~

This is not a production secret. In real environments, source the value from a secret store or environment variable, e.g., `demo.webhook.secret=${WEBHOOK_SECRET}`; ensure raw secrets are never logged.

### 9.6. MockMvc Testing the Entire Boundary

File `src/test/java/demo/csrf/CsrfPolicyTest.java`:

~~~java
package demo.csrf;

import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfPolicyTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    SettingsController settings;

    @BeforeEach
    void resetCount() {
        settings.resetForTest();
    }

    @Test
    void getHealthIsSafeAndPublic() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    @WithMockUser(username = "alice")
    void missingCsrfCannotUpdate() throws Exception {
        mvc.perform(post("/settings"))
            .andExpect(status().isForbidden());

        assertEquals(0, settings.updateCount());
    }

    @Test
    @WithMockUser(username = "alice")
    void invalidCsrfCannotUpdate() throws Exception {
        mvc.perform(post("/settings")
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        assertEquals(0, settings.updateCount());
    }

    @Test
    @WithMockUser(username = "alice")
    void validCsrfCanUpdate() throws Exception {
        mvc.perform(post("/settings").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("updated"));

        assertEquals(1, settings.updateCount());
    }

    @Test
    void signedWebhookIsAcceptedWithoutCsrf() throws Exception {
        String body = "{\"event\":\"created\"}";
        String signature = sign(body);

        mvc.perform(post("/webhooks/vendor")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body)
                .header("X-Webhook-Signature", signature))
            .andExpect(status().isAccepted())
            .andExpect(content().string("accepted"));
    }

    @Test
    void unsignedWebhookIsRejectedWithoutCsrf() throws Exception {
        mvc.perform(post("/webhooks/vendor")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"event\":\"forged\"}"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string("invalid signature"));
    }

    @Test
    void otherPostEndpointStillRequiresCsrf() throws Exception {
        // No controller at /webhooks/other;
        // CsrfFilter blocks POST missing token before reaching MVC.
        mvc.perform(post("/webhooks/other"))
            .andExpect(status().isForbidden());
    }

    private static String sign(String body) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(
            "local-demo-secret-change-before-production"
                .getBytes(StandardCharsets.UTF_8),
            "HmacSHA256"
        ));
        byte[] digest = mac.doFinal(
            body.getBytes(StandardCharsets.UTF_8)
        );
        return "sha256=" + HexFormat.of().formatHex(digest);
    }
}
~~~

Run from the project root with JDK 17+ and Gradle 8.x:

~~~bash
gradle test
~~~

**Expected outcome:** all **7 tests pass**, with the example configuration and declared dependencies. This is an expectation from source code, **not an execution result captured in this lesson**.

### 9.7. Results Table and Significance

| Test | Condition | Expected |
| --- | --- | --- |
| `GET /health` | Anonymous | `200 OK` |
| `POST /settings` | Alice, **no CSRF token** | `403 Forbidden`, counter 0 |
| `POST /settings` | Alice, **wrong token** | `403 Forbidden`, counter 0 |
| `POST /settings` | Alice, **valid token** | `200 OK`, counter 1 |
| `POST /webhooks/vendor` | No CSRF, valid HMAC | `202 Accepted` |
| `POST /webhooks/vendor` | No CSRF, missing HMAC | `401 Unauthorized` |
| `POST /webhooks/other` | No CSRF | `403 Forbidden` before MVC |

The first two tests in the `/settings` group use `@WithMockUser` to isolate CSRF from login flow: **an authenticated user missing CSRF is still blocked**. The webhook tests prove a legitimate exemption carries its own verification mechanism. The alternate-path test proves the exemption does not broaden across all of `/webhooks/**`.

If `.csrf(csrf -> csrf.ignoringRequestMatchers(...))` is removed, tokenless webhook POSTs are blocked by the CSRF filter before the HMAC controller runs. If replaced with `csrf.disable()`, the `/settings` missing-token tests stop proving the CSRF layer is active.

### 9.8. What Must Be Added Before Production?

The demo illustrates only basic HMAC authentication. A production webhook normally also requires:

1. The provider's **official** signature scheme (header format, algorithm, canonical raw body).
2. Signed timestamps and short time windows to prevent replays; never verify only payload HMAC.
3. Safely persisted event IDs or idempotency keys so duplicate requests do not re-run business logic.
4. Secret rotation, no hardcoded secrets, and appropriate network permissions.
5. Request size limits, rate limits, schema validation, and event-type policies.
6. Never logging full payloads, secrets, or raw signatures in public logs.
7. Separating authentication errors from business processing errors, with audit/correlation IDs.

Do not copy the demo HMAC into a production verifier for Stripe/GitHub or a specific provider without implementing their official signing protocol.

## 10. A Purely Stateless API Can Be Split Into a Separate Chain

If a system has both a cookie-based web UI **and** a machine-to-machine API using only Bearer tokens, two separately scoped `SecurityFilterChain`s can be designed. The example below is an **integration guide snippet**, not a standalone runnable application (it needs OAuth2 Resource Server dependencies, a JWT decoder, trusted issuer, and real token config):

~~~java
// ILLUSTRATION: chain applies only to /machine/**,
// authenticating OAuth2 JWT in Authorization header.
// Consider disabling CSRF ONLY if chain uses NO cookies/auto-credentials.

@Bean
@Order(1)
SecurityFilterChain machineApi(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/machine/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .csrf(csrf -> csrf.disable())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain browser(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        // Do not disable CSRF on the browser chain.
        .build();
}
~~~

Corresponding imports include `@Bean`, `@Order`, `SecurityFilterChain`, `HttpSecurity`, `SessionCreationPolicy`, and `Customizer`. An integrated app must remove duplicate chains and test `@Order` precedence.

**Do not apply this pattern if `/machine/**` still accepts browser cookies, Basic auth, or auto-sent credentials.** `STATELESS` speaks only to Spring Security's session strategy; it **does not automatically make every auth mechanism CSRF-safe**.

The benefit of separate chains is preventing a security change for machine APIs from accidentally stripping CSRF protection from the UI. If only one webhook needs an exemption, `ignoringRequestMatchers` as in section 9 is usually simpler and safer.

## 11. Cookie-Based SPAs: Fix Token Delivery, Do Not Rush to Disable CSRF

A Single-Page Application typically sends JSON via `fetch`/Axios. If user identity is still maintained via a session cookie, the browser can automatically attach the cookie on qualifying requests. **SPAs are not automatically immune to CSRF** just because they avoid traditional HTML forms.

Approach:

1. Server generates/stores CSRF tokens.
2. Frontend receives the token via a meta tag, response header, or `XSRF-TOKEN` cookie per config.
3. Frontend attaches the token in a header like `X-CSRF-TOKEN` or `X-XSRF-TOKEN` on POST/PUT/PATCH/DELETE requests.
4. Server validates the token against the expected value.
5. After login/logout or session CSRF state changes, frontend fetches a new token when needed.

Spring Security provides `CookieCsrfTokenRepository`. By default, the cookie is `XSRF-TOKEN` and the corresponding header is `X-XSRF-TOKEN`, though note **the browser sending the cookie alone is insufficient**; the JavaScript client must send the token in the header. In some SPAs, `withHttpOnlyFalse()` lets JavaScript read the CSRF token cookie, which lowers XSS isolation for that specific cookie and must be weighed against XSS risks.

**Spring Security 6 detail:** the default handler uses BREACH masking (`XorCsrfTokenRequestAttributeHandler`) and deferred token loading. When an SPA reads the raw token from a cookie and sends it in a header, token resolution must be configured properly for raw/masked values. Old tokens are also cleared after authentication/logout so clients must fetch a fresh one. Follow the official guide for your exact Spring Security version rather than copying old snippets or disabling BREACH protection without understanding the impact.

For simpler SSR with Thymeleaf, many forms have CSRF tokens auto-integrated by the template engine. If a POST lacks a token, inspect the rendered HTML form and request payload before changing security configuration.

## 12. Can CORS, SameSite, Fetch Metadata, and Origin Replace CSRF?

### CORS

CORS governs which cross-origin requests browsers permit and whether external pages can read responses. A cross-site HTML form with an eligible content type can **be sent** even when the attacker cannot read the response. Thus, "CORS prevents reading the result" **does not** ensure requests create no side effects.

CORS is an important origin control when UI and API live on different origins, yet must never be used as a slogan to replace CSRF tokens across all cookie-based apps.

### SameSite Cookies

`SameSite=Lax` or `Strict` can curb certain cross-site cookie transmission. However:

- **Site** and **origin** are not identical; multiple subdomains can be same-site yet different origins.
- Applications may require cross-site flows, iframes, or third-party integrations.
- Browser behavior/compatibility and cookie configuration affect outcomes.
- Dangerous requests must be tested in real environments rather than assuming one SameSite setting replaces CSRF tokens.

SameSite should be viewed as **defense in depth**. Combine it with `Secure`, `HttpOnly`, TLS, and CSRF tokens matching browser session models.

### Fetch Metadata and Origin/Referer

Checking `Sec-Fetch-Site`, `Origin`, or `Referer` improves detection of untrusted cross-site requests, though missing headers, proxies, redirects, privacy policies, and legitimate integrations must be considered. An extra layer does not mean removing default CSRF tokens is safe. If a design uses origin checks instead of tokens on certain endpoints, thorough threat modeling, compatibility checks, and real tests are required.

### XSS

XSS differs from CSRF: XSS lets malicious code run within the trusted origin and can even read CSRF tokens accessible to JavaScript. Hence CSRF tokens **do not replace** XSS defenses like output encoding, CSP, and controlling untrusted scripts.

## 13. Other Easily Confused Cases

### `permitAll` and Registration POSTs

~~~java
.requestMatchers(HttpMethod.POST, "/register").permitAll()
~~~

This rule requires no logged-in user, yet the POST can still be a browser-submitted state-changing operation. When a request needs CSRF protection, `permitAll` does not remove the token requirement. Depending on threat model, add rate limiting, anti-spam, or email verification—none of which equate to CSRF protection either.

### JSON Content Type

Requiring custom headers or JSON content types is insufficient to declare CSRF meaningless. Inspect all entry points, accepted content types, CORS, and credential behavior—not merely controller DTO types.

### File Upload / Multipart

With multipart browser forms, placing the CSRF token in a header helps avoid parsing the multipart body prior to CSRF validation. If putting the token in the body or query string, evaluate side effects of file parsing and token exposure in URLs/logs. Avoid query-string CSRF tokens whenever form/header approaches fit.

### Session Timeout

If `HttpSessionCsrfTokenRepository` stores tokens in the session and the session expires, submitting an old form may return 403 because the token no longer matches. Handle this via UX to refresh/fetch a new token, prompt re-login, or provide proper access-denied handling. Never "fix" timeouts by disabling CSRF globally.

### "Missing" CSRF Token Due to Deferred Loading

Spring Security 6 may defer loading/generating tokens until accessed. If an SPA relies on cookie tokens, ensure tokens are initialized/issued at the right moment. This is an integration issue, not evidence to disable CSRF.

## 14. Debugging HTTP 403 Step by Step

When a POST returns `403`:

1. **Confirm URL, method, and applied `SecurityFilterChain`** to avoid inspecting the wrong chain.
2. **Confirm authentication:** does the user have a session cookie or Bearer token? Were credentials auto-sent or actively attached in a header?
3. **Check whether the request has a CSRF token:** form field `_csrf` or header `X-CSRF-TOKEN`/`X-XSRF-TOKEN` per config.
4. **Verify token matches session:** did the cookie/session expire, change ID, or did login/logout invalidate the old token?
5. **Check frontend/SPA handler:** sending raw vs. masked token? Was a new token fetched after login/logout?
6. **Check exemption matchers:** right HTTP method and path, no unexpected mismatches?
7. **Verify whether the endpoint truly needs CSRF exemption:** genuine server-to-server webhook, or can browsers still auto-send cookies?
8. **Check authorization and method security:** if CSRF passes yet 403 persists, check authorities/roles or service-layer policies.
9. **Check test cases:** MockMvc tests must add `with(csrf())` for unsafe requests expected to succeed when CSRF is enabled.
10. **Never log raw secrets/tokens:** if enabling DEBUG for security, use controlled environments and redact session/CSRF/bearer credentials.

A good integration troubleshooting step is comparing two requests to the same endpoint with the same authenticated principal: request A missing a token is blocked, request B with a valid token succeeds. That difference shows the CSRF filter works—not a reason to turn it off.

## 15. Checklist for Approving a "Disable CSRF" Request

Before approving a change:

- [ ] Documented the endpoint's **threat model**, knowing whether browsers can auto-send credentials.
- [ ] Zero UI/browser flows use session cookies or automatic Basic/mTLS inside the exempted scope.
- [ ] Verified exact method/path; did not exempt `/api/**` if session-based endpoints exist there.
- [ ] For webhooks, provider-compliant signature auth, timestamp/replay policy, idempotency, and limits exist.
- [ ] For bearer-only APIs, isolated the security chain and ensured no cookie fallback exists.
- [ ] `permitAll` is not used as an excuse that CSRF is unneeded.
- [ ] Login/logout, profile changes, funds, and permission changes remain CSRF-protected if browser session flows.
- [ ] Tested missing, invalid, and valid CSRF tokens; verified state **does not change** when rejected.
- [ ] Tested that the exemption scope does not leak to other endpoints.
- [ ] Verified CORS, SameSite, cookie attributes, and frontend CSRF integration per Spring Security version.
- [ ] Documented the rationale, owner review, and regression tests so future developers do not accidentally widen scope.
- [ ] Did not disable CSRF merely to quickly clear a 403 in a test.

## 16. Self-Check Questions

**Q1.** A `@RestController` accepts POST and authenticates via session cookie. Can CSRF be disabled because it returns JSON?

**Answer:** No. JSON does not determine whether browsers auto-send cookies. If a cross-site request can carry the user's session, proper CSRF protection is still needed.

**Q2.** A partner server webhook has no browser session. When is it reasonable to exempt CSRF?

**Answer:** When the endpoint is tightly scoped and uses proper independent authentication (e.g., HMAC signature, timestamp/anti-replay, idempotency); exempt only the exact required method/path.

**Q3.** Does `permitAll()` on `POST /register` mean CSRF is skipped?

**Answer:** No. Request authorization and the CSRF filter are separate layers.

**Q4.** If an API uses JWTs yet places the JWT inside a cookie, is it safe to exempt CSRF?

**Answer:** No. Browsers can auto-send cookies, including cookies holding JWTs. Evaluate credential behavior and apply matching CSRF defenses.

**Q5.** `@WithMockUser` + POST in MockMvc still gets 403. Why?

**Answer:** The test mocked authentication yet omitted a CSRF token. Use `with(csrf())` for permitted requests, and keep a missing-token test to verify protection.

**Q6.** Why is the demo's HMAC webhook incomplete for production?

**Answer:** Because a valid signature can be replayed without timestamps/replay windows and idempotency. Follow the provider's official signing protocol and secure secret management.

**Q7.** If a site already uses `SameSite=Lax`, can all CSRF checks be deleted?

**Answer:** Not by default. SameSite mitigates some cross-site contexts yet does not replace threat assessments, nor fully handle same-site different-origin cases or special integrations.

## 17. Conclusion and References

**Do not disable CSRF out of habit.** First determine whether requests use credentials auto-attached by browsers. Session-cookie web apps and cookie-based SPAs should keep CSRF. Server-to-server webhooks with signature verification or truly stateless Bearer-only APIs can consider exemptions—yet require **minimal scope**, independent authentication, tests for missing tokens, and checks that exemptions do not leak elsewhere.

**A proper exemption is a decision backed by threat modeling and testing, not a shortcut past a 403 error.**

Official Spring Security documentation:

- [Spring Security — CSRF for Servlet Applications](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — CSRF Threat Model](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html)
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — Servlet Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
