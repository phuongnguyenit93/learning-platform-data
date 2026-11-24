# How a CSRF Token Differs from a Session Cookie and an Access Token

## 1. Objectives and Scope

This lesson belongs to **CSRF** in **Spring Security - fundamentals**. Three values may appear together in a web application yet serve **completely different purposes, storage locations, and verification mechanisms**:

- **CSRF token:** an anti-request-forgery value; the browser must actively send it via an app-controlled form parameter or header, and the server checks it against the expected value.
- **Session cookie (commonly `JSESSIONID`):** the browser automatically sends a session identifier so the server can look up `HttpSession` and authentication state.
- **Access token (commonly a Bearer/OAuth2 token):** a credential enabling a resource server to authenticate or verify API access per issuer, scope, audience, and expiration.

After this lesson, you can:

1. Clearly explain why a **CSRF token is not a login cookie**, and why an **access token is not a CSRF token**.
2. Describe how a forged request can carry a valid session cookie while missing a matching CSRF token.
3. Understand Spring Security Servlet's `CsrfFilter`, `CsrfTokenRepository`, `HttpSessionCsrfTokenRepository`, and `CookieCsrfTokenRepository`.
4. Distinguish sending tokens via **hidden form fields**, **request headers**, or solely **cookies**, and explain why cookies alone fail to stop CSRF.
5. Recognize Spring Security 6 behaviors: **deferred CSRF tokens**, **BREACH-protected** representations, and refreshing tokens after login/logout.
6. Choose CSRF policies for session-based apps, SPAs, and bearer-token APIs based on how browsers actually send credentials.
7. Run a Java 17+/Spring Boot 3.5.x example with login sessions, `GET /csrf`, state-changing POSTs, and `MockMvc` tests verifying missing/invalid/valid CSRF tokens.
8. Spot common pitfalls: disabling CSRF in cookie-login apps, putting tokens in URLs, relying solely on `SameSite`/CORS, confusing 401 vs. 403, or treating CSRF tokens as identity proof.

**Practice scope:** Spring MVC/Servlet with `HttpSecurity`, `SecurityFilterChain`, and form login. Spring WebFlux uses `ServerHttpSecurity` and corresponding reactive components; do not mix Servlet and WebFlux APIs in one example.

## 2. Three "Tokens" Answer Three Different Questions

| Value | Question the server needs to answer | Typically created/verified by |
| --- | --- | --- |
| **CSRF token** | "Does this state-changing request carry anti-forgery proof valid for the app's context?" | `CsrfTokenRepository` + `CsrfFilter` |
| **Session cookie** | "Which server session does this cookie point to, and what identity is logged into it?" | Servlet container, `HttpSession`, `SecurityContextRepository` |
| **Access token** | "Who/which client did a trusted issuer grant this credential to, with what permissions/resources, and is it still valid?" | OAuth2 Resource Server / JWT decoder / opaque introspection |

Imagine a banking app using form login:

```text
Alice's browser                       Server
  Cookie: JSESSIONID=xyz       ────> Find session xyz, restore Authentication=Alice
  X-CSRF-TOKEN: abc...         ────> Compare CSRF token against expected value
  POST /transfer               ────> Check authorization + business logic too
```

Here **both conditions are required**:

- Having a valid login session **does not mean** a POST is permitted if the CSRF token is missing.
- Having a valid CSRF token **does not mean** the caller is logged in or allowed to transfer funds.
- Downstream logic must still check balance, account owner, limits, tenant, recipient, and business rules.

For OAuth2 APIs:

```text
Client ─── Authorization: Bearer ACCESS_TOKEN ───> Resource Server
       │                                           │
       │                                  Verify token/issuer/
       │                                  scope/audience/expiration
       │                                           │
       └────────────── 200 / 401 / 403 <──────────┘
```

An access token **actively** attached to a header by browser JavaScript does not share the "auto-sent" property of session cookies. Still, **if an access token is stored in a cookie and auto-sent by the browser**, the system may still require CSRF protection. Whether the format is JWT or opaque does not by itself determine CSRF exposure.

## 3. CSRF Is an Attack on Auto-Sent Credential Behavior

**Cross-Site Request Forgery (CSRF)** happens when a malicious site causes a victim's browser to send a state-changing request to a target site while the browser **automatically sends held credentials** for the target site (per cookie/browser rules). The server sees a valid session, yet the request **was not intentionally created by the app's legitimate UI**.

Example scenario:

1. Alice is logged into `https://bank.example.test`; her browser holds a valid session cookie.
2. Alice opens an untrusted site. That site builds an HTML form and attempts to send a `POST` to a bank endpoint that modifies data.
3. Depending on cookie `SameSite`, browser context, top-level navigation, and other factors, the request may carry the bank's session cookie even though the form came from another site.
4. If the backend checks only the logged-in session without suitable CSRF protection, the action may execute under Alice's identity.
5. If the backend requires a CSRF token in a request header/form field that the malicious site cannot read or guess, the forged request is rejected.

**SOP/CORS alone are insufficient.** The Same-Origin Policy generally prevents another site from **reading responses**. That does not mean all cross-origin requests are blocked from **sending**; HTML forms can issue requests without reading results. CORS governs relevant cross-origin permissions, not replacing CSRF tokens or equivalent safeguards. Whether browsers send cookies depends on `SameSite`, third-party cookie settings, request type, and context; never assume every cross-site POST carries cookies.

### Example of a Forged Request

```http
POST /account/email HTTP/1.1
Host: bank.example.test
Cookie: JSESSIONID=SESSION_ID

email=attacker%40example.test
```

This is solely an **HTTP illustration**, not an executable command. It shows that a session cookie can identify the user while the request lacks a CSRF parameter/header. A well-protected app blocks it before updating the email. The example does not claim a specific browser always sends cookies across all `SameSite` configurations.

## 4. What Is a CSRF Token and Why Must It Be Sent "Actively"?

In the **synchronizer token pattern**, the server creates an unpredictable token linked to the session context and stores the expected value server-side (typically in the session). A legitimate page or client may receive the token via app responses and place it in a part of the request **not auto-inserted by the browser**:

- Hidden input `_csrf` in an HTML form.
- Header `X-CSRF-TOKEN` or an equivalent configured header when JavaScript calls APIs.
- An equivalent mechanism carefully designed per server policy.

Illustrative valid request:

```http
POST /account/email HTTP/1.1
Host: bank.example.test
Cookie: JSESSIONID=SESSION_ID
Content-Type: application/x-www-form-urlencoded

email=alice%40example.test&_csrf=UNPREDICTABLE_TOKEN
```

**Decisive point:** external sites do not know the session's valid token and cannot simply make the browser attach the right `_csrf`/`X-CSRF-TOKEN`. The server compares the client-supplied value against the expected value; if missing or wrong, the request is blocked.

**Sending the token only in a cookie is not enough.** Browsers attach cookies automatically; if "CSRF defense" checks only whether some cookie exists, malicious sites can exploit automatic cookie delivery too. Even in the double-submit cookie model, the client must **read/obtain a token value and actively send it in a header or form field**, while the server verifies the binding between values. You cannot replace this with "let it pass if the `XSRF-TOKEN` cookie exists".

### How Secret Must a CSRF Token Be?

CSRF tokens must be hard to guess and unreadable by external sites. Never place them in URL queries, as URLs enter history, proxy logs, analytics, `Referer`, or screenshots. Never log full tokens. If the app has same-origin XSS, malicious scripts can read or use CSRF tokens in context; thus **CSRF protection never replaces XSS defense**.

A CSRF token **is not a one-time password by default**: a session-bound token may be reused across multiple POSTs until rotated/invalidated per policy. It is not an idempotency key, does not prevent replay by an actor already controlling the session, and does not prove user consent for a specific transaction amount.

## 5. Where Does a Session Cookie Differ from a CSRF Token?

In typical Spring Security form login, the server stores `SecurityContext` in `HttpSession` for reuse across HTTP requests. The browser only holds the `JSESSIONID` identifier:

```text
Browser                              Server
┌──────────────────────────┐        ┌──────────────────────────────┐
│ Cookie JSESSIONID=xyz    │───────>│ Session xyz                  │
│                          │        │  ├─ SecurityContext          │
│ Hidden/header CSRF token │───────>│  │  └─ Authentication=Alice   │
│ from legitimate page/app │        │  └─ CSRF expected token       │
└──────────────────────────┘        └──────────────────────────────┘
```

| Property | Session cookie `JSESSIONID` | CSRF token |
| --- | --- | --- |
| Purpose | Points to the session to look up | Proves request carries the expected anti-forgery token |
| Who sends it? | Browser **auto-sends** per cookie scope | App must actively place it in form field/header |
| Who creates it? | Container/session manager | `CsrfTokenRepository` |
| Contains user/role? | Usually an opaque ID only | Should not embed identity/business secrets |
| What does server verify? | Session validity, security context/Authentication | Submitted token matches context's expected token |
| Sufficient for API access? | Sufficient for authentication if valid; still needs authorization | No, CSRF token alone does not authenticate users |
| Protects against CSRF? | No | Helpful when properly paired with auto-sent credentials |
| After logout? | Session invalidated; cookie cleanup per config | Associated token usually cleared/invalidated |
| Possible for anonymous users? | Pre-login session can exist | **Yes**: login pages also need CSRF tokens |

**Crucial distinction:** an app can issue a CSRF token **before the user logs in** to protect `POST /login`. This proves a CSRF token **does not equate to access rights** and is not evidence that the token holder is Alice or Bob.

### A CSRF Cookie Is Still a "Cookie", Yet Not a Session Cookie

When using `CookieCsrfTokenRepository`, Spring Security can store the CSRF token in an `XSRF-TOKEN` cookie. This cookie differs from the `JSESSIONID` session cookie:

- `JSESSIONID`: points to the server session used for login.
- `XSRF-TOKEN`: carries the CSRF token per chosen repository; JavaScript may need to read it to send back in `X-XSRF-TOKEN`.
- The server still validates the token actively sent via the matching header/form field, **not just the presence of `XSRF-TOKEN`**.
- `XSRF-TOKEN` **does not** prove valid Authentication on its own, nor does it replace session credentials or access tokens.

Do not assume any cookie with "token" in its name is used for logging in.

## 6. How Does an Access Token Differ from Both Values Above?

An **Access token** is issued by an Authorization Server or trusted authentication system for resource access rights, not merely for a web session form. It is commonly sent as:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
```

The Resource Server verifies issuer/signature/expiry/audience/scopes or introspects opaque tokens depending on configuration. Afterward, it checks owner/tenant/roles per endpoint policy.

Comparison:

| Concept | Access token | CSRF token |
| --- | --- | --- |
| Issued by | Authorization Server/IdP or equivalent system | Application or `CsrfTokenRepository` |
| Proves | Right to use API within token's scope | Anti-forgery token for request matching context |
| Can carry claims? | JWTs hold claims like `sub`/`aud`/`scope`; opaque tokens require external lookup | Usually an unpredictable value with no privilege claims |
| Where presented? | Commonly `Authorization: Bearer ...` | `_csrf` or `X-CSRF-TOKEN`/`X-XSRF-TOKEN` |
| Valid for authentication? | Can authenticate Bearer requests | **No** |
| Replaces CSRF protection? | Not automatically; depends on whether browsers auto-send credentials | Yes when implementing anti-CSRF patterns properly |
| Risk if leaked | Usable as a credential until expiry/revocation | Attacker can bypass CSRF layer for matching context |
| Client storage | Needs careful design per client and threat model | Can live in HTML/page state, session, or cookie per repository |

### Does a JWT Replace a CSRF Token?

**No.** A validly signed JWT access token proves issuer and claims, not that the request was deliberately created by a legitimate UI. If a JWT is stored in a cookie and auto-sent, forged requests can still carry that JWT cookie.

Conversely, if browser JavaScript explicitly attaches a Bearer token in the `Authorization` header, other sites normally cannot make the browser attach that Bearer token on cross-site forms. When an API uses no auto-sent **ambient credentials**, the CSRF threat model differs from session cookies. Still, you must defend against XSS, token theft, CORS, replay, scope abuse, and sensitive actions. **Never use the slogan "JWT means always disable CSRF".**

### OAuth2 Access Tokens and Refresh Tokens Also Differ

A **Refresh token** is used to request new access tokens from the Authorization Server, with its own storage/rotation/revocation policies. It is not a CSRF token. A browser SPA might hold access/refresh tokens or use a BFF/session; choosing the right defense depends on how authentication **is transmitted on requests**.

## 7. Anti-CSRF Implementation Patterns

### 7.1. Synchronizer Token Pattern — Typical for Session-Based Web

1. Server stores the expected token in the session.
2. Web pages receive the token in HTML/form attributes or JSON/headers from an appropriate endpoint.
3. POST/PUT/PATCH/DELETE requests carry the token in `_csrf` or an app-set header.
4. `CsrfFilter` compares the submitted token against the expected token; missing/invalid gets 403.

This fits `HttpSession` and form login well. With default Spring Security Servlet, `HttpSessionCsrfTokenRepository` stores expected tokens in the session.

### 7.2. CookieCsrfTokenRepository — CSRF Value in Cookie, Resent by Client

Illustrative configuration:

```java
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
);
```

This is a **fragment**, requiring `import org.springframework.security.web.csrf.CookieCsrfTokenRepository` inside an actual `SecurityFilterChain`.

With this repository, the cookie is normally named `XSRF-TOKEN`, and the value is sent back in the `X-XSRF-TOKEN` header or `_csrf` parameter.

**Special note for Spring Security 6:** by default `XorCsrfTokenRequestAttributeHandler` creates a masked representation with randomness to protect against BREACH. An SPA reading the **raw token from the cookie** and returning it in a header is not automatically compatible with the default XOR handler's decoding flow. Spring Security docs provide a **custom SPA `CsrfTokenRequestHandler` setup** handling raw tokens from headers and masked tokens from forms. Never just add `withHttpOnlyFalse()` and assume the SPA works; configure the right handler and test real requests.

`withHttpOnlyFalse()` lets JavaScript read the CSRF cookie and construct the header. That **does not mean** disabling `HttpOnly` on the `JSESSIONID` login cookie. Never make the session cookie readable by scripts merely for CSRF convenience.

### 7.3. Signed Double-Submit Cookie

In architectures preferring not to store CSRF tokens server-side, clients receive a CSRF cookie signed and **bound to session/context** with HMAC, then echo the token in a header/form. The server verifies structure, HMAC, and context binding.

**Do not implement naive double-submit** checking only "cookie equals header" without mitigating cookie injection or subdomain-controlling attackers. OWASP recommends the **signed double-submit cookie** with session binding when choosing this approach.

**Distinction:** `CookieCsrfTokenRepository` is a Spring API storing/reading tokens in cookies per framework contract. It does not by itself guarantee your entire deployment meets OWASP's **HMAC session-bound signed double-submit** standard. If strong cookie-injection defense is required, design and audit against your threat model.

### 7.4. Origin/Referer/Fetch Metadata Checks

`Origin`, `Referer`, `Sec-Fetch-Site`, and `Sec-Fetch-Mode` can help detect cross-site requests and apply *defense in depth*. They have limits around browsers, proxies, redirects, and missing headers; never replace all CSRF defenses with a single header check.

`SameSite=Lax` or `Strict` cookies also curb certain cross-site cookie-carrying requests, yet **same-site is not always same-origin** and subdomains can still play a role. CSRF tokens, Origin/Fetch Metadata, and SameSite should be viewed as layered defenses.

## 8. Spring Security 6 Mechanics: CsrfFilter, Repository, and Request Handler

For Servlet, key components:

| Component | Responsibility |
| --- | --- |
| `CsrfFilter` | Identifies requests needing CSRF protection and compares tokens |
| `CsrfTokenRepository` | Generates, stores, and loads expected tokens |
| `HttpSessionCsrfTokenRepository` | Stores expected token in `HttpSession` (common default) |
| `CookieCsrfTokenRepository` | Stores/loads CSRF token via cookie |
| `CsrfTokenRequestHandler` | Exposes token on requests and resolves client-submitted values |
| `XorCsrfTokenRequestAttributeHandler` | Spring Security 6 default handler with random masking against BREACH |
| `CsrfAuthenticationStrategy` | Clears old tokens on successful authentication in relevant flows |
| `CsrfLogoutHandler` | Clears old tokens on logout |
| `AccessDeniedHandler` | Handles missing/invalid tokens, typically returning 403 |

Diagram:

```text
HTTP POST /api/counter
   ├─ Browser auto-sends Cookie JSESSIONID=...
   ├─ Browser/app actively sends _csrf or X-CSRF-TOKEN
   │
   ▼
CsrfFilter
   ├─ Check if method needs CSRF?
   │     ├─ GET/HEAD/OPTIONS/TRACE usually no
   │     └─ POST/PUT/PATCH/DELETE usually yes
   │
   ├─ Fetch expected CsrfToken from CsrfTokenRepository
   ├─ Read caller-submitted token via CsrfTokenRequestHandler
   ├─ Compare
   │     ├─ Missing/wrong → 403, do not invoke state-changing endpoint
   │     └─ Valid → allow filter chain to proceed
   │
   ▼
Authentication / Authorization / Controller / Service
   ├─ Anonymous/insufficient permissions → blocked further
   └─ Authorized → process business logic
```

Actual filter ordering may include many other filters/checkpoints. The diagram illustrates **two independent conditions**, not a claim that CSRF always runs immediately before every authentication mechanism in all custom setups.

### 8.1. Which Requests Are Checked?

Spring Security by default requires CSRF for *unsafe* HTTP methods (usually **POST, PUT, PATCH, DELETE**) and exempts **GET, HEAD, OPTIONS, TRACE**. Hence, **GET must not mutate data or create sensitive side effects**. If you write a `GET /delete-account` endpoint to delete accounts, the default CSRF filter will not protect it because GET is treated as safe.

Also avoid writing `csrf(csrf -> csrf.disable())` globally just because a JSON endpoint "looks like an API". If browser session cookies or refresh cookies are still used, CSRF may still apply.

### 8.2. Deferred Tokens in Spring Security 6

Spring Security 6 defers loading CSRF tokens until needed, avoiding forcing session reads on every simple GET. When a page needs to render a token or an unsafe request needs verification, the token is loaded/materialized.

Consequences:

- Do not assume every `GET /public` creates a session or CSRF cookie.
- A `GET /csrf` endpoint can be actively called when the frontend needs a token.
- Once rendered in an HTML form or JSON response, the system may create/store the token in the repository.

### 8.3. BREACH Protection: Token Seen in HTML May Change While Session Doesn't

`XorCsrfTokenRequestAttributeHandler` can represent the token **masked/encoded with per-request randomness**. Thus, the token visible in hidden fields can vary across renders while the internal expected token stays stored in the session.

**Do not write tests forcing `_csrf` strings across two pages to be identical.** What matters is that a token retrieved from a valid response is accepted by the server when properly submitted back.

For SPAs using raw cookie tokens, configure the proper handler (section 7.2). This is a common migration trap from Spring Security 5 to 6.

### 8.4. On Login or Logout, a Fresh Token Is Needed

Upon successful authentication, `CsrfAuthenticationStrategy` clears old tokens in relevant flows. `CsrfLogoutHandler` also clears tokens on logout. Frontends must not cache old tokens in memory and keep POSTing without refreshing.

If the app exposes `GET /csrf`, the client can re-call it **after login** and **after logout** to get a fresh token. With server-rendered form login, the new page typically provides a token for the current context. If an SPA sees CSRF 403s after login, inspect the token lifecycle before "fixing" it by turning off CSRF.

### 8.5. Blocked CSRF Is Typically 403

When a token is missing or wrong, `CsrfFilter` throws `AccessDeniedException`, handled by `AccessDeniedHandler` (defaulting usually to **403 Forbidden**). This is not necessarily a "wrong password" or "missing role" error. Classify causes via safe logging/observability.

If credentials are absent even with a valid CSRF token, the request can still be redirected to login or return 401 depending on the auth mechanism. **Valid CSRF grants no permissions.**

## 9. Runnable Java 17 Example: Session Cookie, CSRF Endpoint, and State-Changing POST

This lab uses **Java 17+**, **Spring Boot 3.5.12**, **Spring Security 6.x**, **Gradle 8.4+**. A demo account logs in via form and session cookie; the API mutates a counter **specific to that user**.

- `GET /public`: no login needed.
- `GET /csrf`: lets valid clients retrieve a token for forms/requests; this endpoint may create a session to store the token even while anonymous.
- `GET /account`: requires login; responds `hello alice`.
- `GET /api/counter`: requires login and returns counter.
- `POST /api/counter`: requires login **and** valid CSRF token; increments counter.
- `POST /login`/`POST /logout`: handled by Spring Security with default CSRF protection.

**The counter is purely in-memory demo data.** It clearly shows requests receiving 403 are blocked from changing state; real apps need databases, resource authorization, and transaction controls.

### 9.1. Project Structure

```text
csrf-three-values-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/csrfvalues/
    │   ├── CsrfValuesApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/com/example/csrfvalues/
        └── CsrfSeparationTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'csrf-three-values-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Because the app uses Spring, dependencies must be on the classpath. Use Gradle/Wrapper, not bare `javac` and `java` without libraries.

### 9.2. Startup Class

**`src/main/java/com/example/csrfvalues/CsrfValuesApplication.java`**

```java
package com.example.csrfvalues;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfValuesApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfValuesApplication.class, args);
    }
}
```

### 9.3. SecurityFilterChain: Do Not Disable CSRF

**`src/main/java/com/example/csrfvalues/SecurityConfiguration.java`**

```java
package com.example.csrfvalues;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public", "/csrf")
                    .permitAll()
                .requestMatchers("/account", "/api/counter")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form.permitAll())
            .logout(logout -> logout.permitAll())
            .csrf(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
```

Explanation:

1. CSRF protection **remains enabled by default**; `.csrf(withDefaults())` just writes it explicitly. For browser POSTs using session cookies, `CsrfFilter` must verify the token.
2. `GET /csrf` is open so an unauthenticated client can obtain a token for **`POST /login`**. This **creates no Authentication**; it only creates/reads a CSRF token. In production sites, control CORS/Origin, caching, and response sensitivity appropriately.
3. `/account` and `/api/counter` require authentication; a CSRF token is not enough to bypass this requirement.
4. Form login uses `HttpSession` and session cookies in the Servlet container; `BCryptPasswordEncoder` hashes the demo password when building the user store. Password `alice123` is for learning only, never real environments.
5. `/login` and `/logout` are handled by Spring Security filters. With default CSRF, those POSTs also need valid tokens; no manual controller is needed.
6. `anyRequest().denyAll()` is a fallback for uncategorized routes; it does not make GET safe if a controller has side effects.
7. OAuth2 Resource Server is omitted from this demo because the goal is **separating CSRF tokens from session cookies**. The access token discussions in sections 6 and 11 are conceptual comparisons; do not claim this demo issues JWT/Bearer tokens.

**Do not expose this demo directly to the public Internet:** it lacks HTTPS, production identity stores, rate limiting, auditing, and many necessary safeguards.

### 9.4. Controller: Returning CSRF Token, Reading, and Incrementing Counter

**`src/main/java/com/example/csrfvalues/DemoController.java`**

```java
package com.example.csrfvalues;

import java.security.Principal;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final ConcurrentHashMap<String, AtomicInteger> counters =
        new ConcurrentHashMap<>();

    private AtomicInteger counterFor(Principal principal) {
        return counters.computeIfAbsent(
            principal.getName(), name -> new AtomicInteger()
        );
    }

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }

    @GetMapping("/account")
    public String account(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/api/counter")
    public Map<String, Object> current(Principal principal) {
        return Map.of(
            "user", principal.getName(),
            "counter", counterFor(principal).get()
        );
    }

    @PostMapping("/api/counter")
    public Map<String, Object> increment(Principal principal) {
        return Map.of(
            "user", principal.getName(),
            "counter", counterFor(principal).incrementAndGet()
        );
    }
}
```

Spring Security provides `CsrfTokenArgumentResolver` for `CsrfToken` in Servlet controllers, so `GET /csrf` can return JSON like:

```json
{
  "parameterName": "_csrf",
  "headerName": "X-CSRF-TOKEN",
  "token": "SESSION_RANDOM_VALUE"
}
```

The value here is solely a **structural example**, not a valid token to copy. Real tokens are framework-generated and may be masked/encoded differently across responses in Spring Security 6.

Do not return `JSESSIONID`, `SecurityContext`, passwords, access tokens, or internal details from `GET /csrf`. This endpoint can apply a no-store cache policy and require clients to re-fetch after login/logout. A production API can tailor its CSRF endpoint to the frontend; this example focuses purely on the concepts.

### 9.5. Running and Observing

Requirements: JDK 17+, compatible Gradle 8.4+, and free port 8080. Inside `csrf-three-values-demo`:

```bash
gradle test
gradle bootRun
```

If a compatible Gradle Wrapper is present, replace with `./gradlew test` / `./gradlew bootRun` (Linux/macOS) or `gradlew.bat test` / `gradlew.bat bootRun` (Windows).

Open a browser to `http://localhost:8080/account`, sign in as `alice` / `alice123` via the default form.

- After login, `GET /account` returns body `hello alice`.
- `GET /api/counter` returns JSON like `{"user":"alice","counter":0}` on the first read before any successful POST.
- Sending `POST /api/counter` relying solely on the session cookie **without a CSRF token** returns **403**, and the counter stays unchanged.
- Sending POST with the same session cookie **and a valid CSRF token** in `X-CSRF-TOKEN` or `_csrf` returns 200 and increments the counter.
- Sending a CSRF token **without a valid login session** still does not grant POST access, because the HTTP rule requires authentication.

Simulating via browser DevTools requires keeping the same session cookie and fetching the token **after logging in**. If you get a 403 due to a stale token, reload `/csrf`; do not disable CSRF. With an `HttpOnly` cookie, browser JavaScript cannot directly read `JSESSIONID`, yet the browser sends cookies per scope. That is precisely why the site needs a separate CSRF layer for state-changing requests.

### 9.6. Illustrative HTTP Requests

**Same session cookie, missing CSRF token:**

```http
POST /api/counter HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=SESSION_ID

```

Expect **403 Forbidden** under the demo configuration. The session cookie in the snippet is a symbol, not a real credential.

**Same session cookie, valid CSRF token:**

```http
POST /api/counter HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=SESSION_ID
X-CSRF-TOKEN: CSRF_TOKEN_FROM_CURRENT_SESSION

```

Expect **200 OK** if the session is logged in and the token is valid. You cannot copy `CSRF_TOKEN_FROM_CURRENT_SESSION` as a literal string; use the live token of the active context.

**Only CSRF token without a login session:**

```http
POST /api/counter HTTP/1.1
Host: localhost:8080
X-CSRF-TOKEN: SOME_TOKEN

```

Even assuming the token validates against an anonymous context, the request still **lacks Alice's Authentication**. Spring form-login normally redirects to `/login`, with no reason to permit data mutation.

### 9.7. Automated Testing with Spring Security Test and MockMvc

**`src/test/java/com/example/csrfvalues/CsrfSeparationTests.java`**

```java
package com.example.csrfvalues;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfSeparationTests {

    @Autowired
    MockMvc mvc;

    private MockHttpSession loginAlice() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("alice").password("alice123")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void publicEndpointNeedsNoLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void csrfTokenEndpointIsAvailableBeforeLogin() throws Exception {
        mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.parameterName").value("_csrf"))
            .andExpect(jsonPath("$.headerName").value("X-CSRF-TOKEN"))
            .andExpect(jsonPath("$.token").isNotEmpty());
    }

    @Test
    @WithMockUser(username = "alice")
    void sessionAuthenticationWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/counter"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void invalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/counter").with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void validCsrfWithAuthenticationIsAllowed() throws Exception {
        mvc.perform(post("/api/counter").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"))
            .andExpect(jsonPath("$.counter").isNumber());
    }

    @Test
    void csrfTokenAloneDoesNotAuthenticateUser() throws Exception {
        mvc.perform(post("/api/counter").with(csrf()))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "alice123"))
            .andExpect(status().isForbidden());
    }

    @Test
    void realLoginSessionStillNeedsCsrfForUnsafeRequest()
            throws Exception {
        MockHttpSession session = loginAlice();

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("hello alice"));

        mvc.perform(post("/api/counter").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/counter").session(session).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void logoutRequiresCsrfEvenWithLoggedInSession()
            throws Exception {
        MockHttpSession session = loginAlice();

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk());

        mvc.perform(post("/logout").session(session).with(csrf()))
            .andExpect(status().is3xxRedirection());
    }
}
```

**Significance of the tests:**

- `@WithMockUser` establishes a valid security context for a test, **without simulating a real browser's `JSESSIONID` cookie**. This lets the missing/bad token tests cleanly isolate **authentication** from **CSRF protection**.
- `spring-security-test`'s `csrf()` supplies a matching CSRF token for MockMvc requests to test the success branch; `csrf().useInvalidToken()` tests the rejection branch.
- `formLogin()` submits a login request with a valid CSRF token; the returned session simulates `HttpSession` reuse across subsequent requests.
- `realLoginSessionStillNeedsCsrfForUnsafeRequest` is the most crucial check: **even with an authenticated session, missing a CSRF token returns 403**, while the same session succeeds when carrying a token.
- `csrfTokenAloneDoesNotAuthenticateUser` proves the converse: **having a CSRF token without logging in cannot mutate data**.
- `logoutRequiresCsrfEvenWithLoggedInSession` highlights that logout is also a sensitive action guarded by CSRF protection.
- Tests assert status codes and returned data rather than forcing random token strings to stay fixed.
- These tests **do not replace** real browser verification for `Secure`/`SameSite` cookies, CORS, token masking, TLS, or access-token policies. Separate integration/security tests are required for those areas.

## 10. FAQ: Why Is a CSRF Token Still Needed When You Have a Cookie?

Because the browser itself auto-sends cookies. If a cookie suffices to recognize Alice, another site can abuse the browser as a "request-sending proxy under Alice's identity" in scenarios where cookies are attached.

Putting a CSRF token in a **non-auto-sent form field/header** raises the bar: another site cannot trivially craft a request carrying the exact token. It does not authenticate identity—it only safeguards **request origin authenticity in cookie-authentication contexts** per your threat model.

### Why Can a CSRF Token Not Replace an Access Token?

If a client carries only `X-CSRF-TOKEN` with no session cookie or bearer credentials, the Resource Server cannot tell which authorized user made the call and cannot derive `sub`/`roles`/`scope` from a CSRF token.

A leaked CSRF token in an attacker's hands could aid request forgery **when combined** with other conditions, yet it **is not** an OAuth2 access token. Never accept `_csrf` values in `Authorization: Bearer` or act as an identity provider based solely on CSRF tokens.

### Why Does an Access Token Not Automatically Replace a CSRF Token?

Because an access token answers "is this credential valid?". If the browser auto-sends that credential (e.g., a JWT in a cookie), cross-site request risk persists. Even with signed JWTs, the backend still needs anti-CSRF policies matching how browsers transmit credentials.

### Does Fetching a CSRF Token via GET Defeat Its Purpose?

Not necessarily. Legitimate same-origin apps need a way to obtain tokens before issuing POSTs. In the synchronizer token pattern, tokens can be embedded in HTML forms or returned via `GET /csrf`. Cross-origin attackers normally cannot read the app's responses when SOP/CORS are configured properly, and cannot guess random tokens.

However, overly permissive CORS **with credentials**, same-origin XSS, logged tokens, or exposing the CSRF endpoint over insecure channels can undermine protection. Keep `/csrf` responses private per threat model, avoid inappropriate caching, and never confuse `permitAll` with "allow foreign origins to read data".

### Is the `XSRF-TOKEN` Cookie a Session Cookie?

No. It holds the CSRF token when using `CookieCsrfTokenRepository`. The `JSESSIONID` session cookie normally points to the `HttpSession` holding login state. Each cookie has its own name, role, `HttpOnly` attribute, and lifecycle policy. An SPA may read the CSRF cookie while still being **barred** from reading the `HttpOnly` session cookie.

## 11. After Login, Logout, or Session Expiration

### Upon Successful Login

- The session ID may rotate to prevent session fixation.
- Spring Security may clear old CSRF tokens via `CsrfAuthenticationStrategy`.
- A frontend retaining an old token obtained from the login page can hit 403 on post-login POSTs.
- For server-rendered HTML apps, the new page should receive an updated token. For SPAs, actively re-call `/csrf` after authentication success.

**Do not rely on token immutability:** raw expected tokens, masked tokens rendered in HTML, and post-login tokens are distinct concepts that can differ.

### Upon Logout

- Spring Security protects `POST /logout` with CSRF by default when CSRF is enabled.
- `CsrfLogoutHandler` clears the associated token, and other logout handlers may invalidate `HttpSession` and clear `SecurityContext`.
- Pre-logout tokens should not be reused by the frontend when starting a new session.
- Web session logout **does not automatically revoke JWT access/refresh tokens** issued by an IdP; dedicated revocation/SSO logout mechanisms are needed.

### Upon Session Timeout

- The browser might still send an old `JSESSIONID` cookie after the server-side session has expired.
- The expected CSRF token in `HttpSession` is also gone, so a POST from a stale tab may receive **403 Missing/Invalid CSRF** before the user sees a login redirect.
- The UI should handle this by prompting re-login and fetching a fresh token, rather than blaming every 403 on "missing role".
- A GET to a form/login page may generate a new token depending on config; verify the right session and avoid sending old tokens on new sessions.

### Limits of "Token Rotation"

Spring Security can refresh/clear tokens on security events like login/logout. That differs from **per-request one-time CSRF tokens**; do not deduce from changing BREACH-masked strings that the server-side token rotates on every request. And never rely on CSRF tokens to stop duplicate submissions of an already-authenticated transaction; use proper idempotency keys or transaction authorization.

## 12. HTTP 401, 403, and Business Permissions

| Scenario | Typical handling in demo | Meaning |
| --- | --- | --- |
| `GET /account` without session | 302 to `/login` | Unauthenticated for form login |
| `GET /account` with valid session | 200 | Authenticated |
| `GET /csrf` unauthenticated | 200 + CSRF token | Token issued only, no user privileges |
| `POST /api/counter` with session, missing `_csrf`/header | 403 | Blocked by CSRF filter |
| `POST /api/counter` with session, wrong CSRF token | 403 | Blocked by CSRF filter |
| `POST /api/counter` with session and valid CSRF | 200 | Passed both CSRF and authentication |
| `POST /api/counter` with CSRF, unauthenticated | 302 to `/login` with form login | CSRF does not authenticate user |
| `POST /login` missing CSRF | 403 | Not "wrong password" |
| `POST /logout` missing CSRF | 403 | Logout rejected |
| `GET /api/counter` logged in | 200 | GET normally needs no CSRF if non-mutating |

This table reflects **the demo setup in section 9**. OAuth2 Resource Server or HTTP Basic apps may return **401** instead of redirecting to form login. When an authenticated user lacks permissions on a resource, **403** can come from authorization rather than CSRF; identify which filter/exception actually blocked the request.

**Never expose "CSRF invalid" error codes alongside raw expected tokens in public responses** if it leaks secrets; internal logs should avoid printing full tokens. For JSON APIs, return consistent error contracts without masking security issues via automatic POST retries.

## 13. When Should CSRF Protection Be Kept or Omitted?

| Architecture | Browser auto-sends credentials? | Guidance |
| --- | --- | --- |
| Form login + session cookie | Yes | **Keep CSRF protection** for unsafe methods |
| Server-rendered MVC + session cookie | Yes | **Keep CSRF**; forms carry hidden tokens |
| SPA + session cookie/BFF cookie | Yes | **Keep CSRF**; design token header endpoints and SPA handlers properly |
| SPA storing JWT in auto-sent HttpOnly cookie | Yes | **CSRF risk persists**; choose appropriate defense |
| API with client-attached Bearer token solely in Authorization header | Usually not like cookies | May consider omitting CSRF for that endpoint if zero ambient credentials exist and threat model allows |
| Service-to-service mTLS/Bearer without browser | Not via browser cookies | CSRF usually not the primary threat; still protect authn/authz/token replay |
| Hybrid cookie + Bearer application | Yes, on some routes | Configure per **SecurityFilterChain** or real matchers; never disable globally at random |

Naming an API "REST" or returning JSON does not stop credentials from auto-sending. If browser cookie sessions access JSON APIs, CSRF can still apply.

**Be cautious with HTTP Basic authentication in browsers:** browsers can cache and auto-send Basic credentials per origin/realm. An API using HTTP Basic is not automatically safe from CSRF just because credentials live in the `Authorization` header. Analyze how clients transmit headers on cross-site requests.

### Using Multiple SecurityFilterChains

You can have a browser chain using form login + CSRF and an API chain using stateless bearer-only policies. `securityMatcher` decides which chain handles a request; `@Order` places specific chains ahead of general catch-all chains. When omitting CSRF on a chain, prove that chain accepts zero browser ambient credentials and has no endpoints needing CSRF protection. Do not confuse first-chain matching with `requestMatchers` authorization inside a chain.

**Never drop CSRF on `POST /login` or `POST /logout`** without analyzing login/logout CSRF. Spring Security protects these by default in Servlet apps.

## 14. Practical Deployment Protection Checklist

1. **Identify real credentials:** session cookies, header access tokens, cookie-stored bearers, browser Basic, or hybrids.
2. **Classify unsafe operations:** POST/PUT/PATCH/DELETE, ensuring no GET causes sensitive side effects.
3. **Place CSRF tokens properly:** client-submitted tokens belong in form fields or headers, never solely in cookies and never in URL queries.
4. **Keep tokens unpredictable and unexposed in logs/caches/analytics:** prevent leakage to external origins or via `Referer`.
5. **Store expected tokens in proper repositories:** `HttpSession`, cookies, or audited custom HMAC designs; never reuse the session ID.
6. **For Spring Security 6 SPAs:** verify XOR/BREACH handlers, raw cookie headers, and fetching fresh tokens after login/logout.
7. **Session cookies:** proper `Secure`, `HttpOnly`, `SameSite`, and `Path`/`Domain` scoping. SameSite is an auxiliary layer, not the complete solution.
8. **CORS/Origin/Fetch Metadata:** configure trusted origins; never combine wildcards with credentials carelessly.
9. **Distinguish 401 vs. 403:** CSRF failures, authentication failures, and authorization failures follow distinct branches.
10. **Consider XSS:** prevent script injection via escaping, CSP, and dependency hygiene; CSRF tokens offer no defense if attackers run same-origin code.
11. **Negative testing:** session present without token; wrong token; valid token while anonymous; stale token after logout/login.
12. **Enforce permissions in services:** CSRF tokens prove neither owner/tenant/role nor replace authorization.
13. **Real browser tests:** cookie flags, SameSite, subdomains, SSO, reverse proxies, CSRF token generation, and login/logout flows.
14. **Never hardcode tokens:** generate via framework, bind to right context, rotate/expire per policy.
15. **Never assume blanket safety:** verify against the exact browsers, paths, cookies, and auth mechanisms your application supports.

## 15. Scenario Exercises with Solutions

**Q1.** Alice has a valid `JSESSIONID`. Why can a POST missing a CSRF token still get 403?

**Answer:** the cookie only restores Alice's Authentication; it does not prove the request came from a legitimate page. `CsrfFilter` requires an actively submitted CSRF value matching the session and blocks if missing.

**Q2.** A request carries only a valid `X-CSRF-TOKEN` header with no login session. Is it automatically allowed to update data?

**Answer:** no. A CSRF token does not authenticate users; the backend still requires separate Authentication and authorization. With form login, it usually redirects to `/login` once CSRF passes.

**Q3.** Can `JSESSIONID`'s value be used as `_csrf`?

**Answer:** no. Copying the session ID as a CSRF token turns a sensitive credential identifier into data exposed in HTML/requests, creating session exposure risk and breaking separation of concerns. Use independent framework-generated CSRF tokens.

**Q4.** If the browser auto-sends the `XSRF-TOKEN` cookie, why is the `X-XSRF-TOKEN` header still needed?

**Answer:** because auto-sent cookies cannot distinguish forged requests; a header created by the same-origin app proves the client could read/obtain the token, which the server then verifies. In Spring Security 6, pair it with a handler supporting raw/masked tokens.

**Q5.** Why does putting a JWT in a cookie not eliminate CSRF?

**Answer:** because browsers can auto-send the JWT cookie on cross-site requests per scope/SameSite; the API may execute requests under the user's identity without the attacker ever reading the JWT. CSRF depends on *how credentials are sent*, not *JWT format*.

**Q6.** An SPA attaches `Authorization: Bearer ...` headers itself and the API uses no login cookies. Must CSRF be enabled just like form login?

**Answer:** possibly not under an appropriate threat model, since browsers don't automatically attach the SPA's header token on cross-origin requests. Still check Basic auth, refresh-cookie endpoints, XSS, CORS, and alternate auth paths; never generalize blindly across all routes.

**Q7.** Why can HTML form tokens differ across two separate GETs in Spring Security 6?

**Answer:** `XorCsrfTokenRequestAttributeHandler` produces rendered values with random masking to counter BREACH. Do not conclude the underlying expected raw token or session changed on every request.

**Q8.** Why might an SPA get 403 right after login even though it fetched a CSRF token before login?

**Answer:** the old token may have been cleared by `CsrfAuthenticationStrategy` after authentication. The SPA needs to fetch a fresh token post-login, use a suitable handler, and send the right header.

**Q9.** If a server lets `GET /delete-account` delete accounts, will the default CSRF filter block that request?

**Answer:** you cannot rely on it because GET is treated as safe and normally exempt from CSRF checks. Fix the API so state-changing actions use appropriate unsafe methods with proper authorization and CSRF.

**Q10.** Why are `SameSite` cookies and CORS not standalone CSRF solutions?

**Answer:** `SameSite` has browser limits and relies on same-site boundaries; CORS largely governs response reading/sharing rather than blocking all form/request submissions. CSRF tokens or equivalent safeguards must be evaluated in the threat model.

**Q11.** If an access token has a valid `orders.read` scope, does that guarantee permission to read another user's orders?

**Answer:** no. Access tokens prove issuer-granted credentials/scopes, while resource-level owner/tenant checks must be enforced by the service. CSRF tokens cannot replace that policy either.

**Q12.** Does storing the CSRF token in a JavaScript-readable cookie require disabling `HttpOnly` on the session cookie?

**Answer:** no. `withHttpOnlyFalse()` in `CookieCsrfTokenRepository` applies only to the CSRF cookie when the frontend must read it. Session cookies should remain `HttpOnly` whenever appropriate.

**Q13.** When a session expires, the browser still sends the old cookie and token from a stale tab. What can happen?

**Answer:** the server no longer has the expected token/Authentication for the old session, so unsafe requests may get 403. The frontend must sync login status, fetch a new token, and let the user re-authenticate.

**Q14.** Can a CSRF token replace an idempotency key to prevent double-clicking a transfer button?

**Answer:** no. Session CSRF tokens are normally reusable within the session and only prevent forged requests. Preventing duplicate transactions requires dedicated idempotency/transaction controls.

## 16. Lesson Summary

- **Session cookies** answer "which authenticated session does this request belong to?"; browsers can **auto-send** cookies.
- **CSRF tokens** answer "does this unsafe request carry valid anti-forgery proof?"; apps must **actively send** tokens via headers/form fields; tokens are neither identity nor permissions.
- **Access tokens** are API credentials with scopes/audience/expiry verified by Resource Servers; they do not substitute for CSRF tokens when auto-sent by browsers in cookies.
- Spring Security Servlet uses `CsrfFilter` and `CsrfTokenRepository`; `HttpSessionCsrfTokenRepository` is the typical default, while `CookieCsrfTokenRepository` is an alternative.
- **Spring Security 6** features deferred loading and `XorCsrfTokenRequestAttributeHandler` for BREACH protection; SPAs reading raw cookie tokens need an appropriate handler.
- **CSRF and Authentication are two independent layers:** having a session without CSRF → can yield 403; having CSRF without logging in → still grants no access.
- **Login/logout and unsafe methods** need proper protection; frontends may need to fetch fresh tokens after login/logout/session timeouts.
- **CSRF depends on how browsers send credentials**, not on cookie names, JWTs, or whether endpoints return JSON.
- Maintain CSRF protection, SameSite, cookie flags, CORS/Origin/Fetch Metadata, XSS defenses, and resource-level authorization as coordinated defense layers.
- Write tests verifying both permitted and rejected paths; production also requires real browser and infrastructure testing.

## References

- Spring Security — CSRF Servlet, repositories, deferred tokens, BREACH, SPA, /csrf endpoint and tests: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — CSRF overview and synchronizer token pattern: https://docs.spring.io/spring-security/reference/features/exploits/csrf.html
- Spring Security — Spring Security 6 CSRF migration: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/exploits.html
- Spring Security — MockMvc CSRF testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — Form login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — Logout and CSRF: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- OWASP — Cross-Site Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
