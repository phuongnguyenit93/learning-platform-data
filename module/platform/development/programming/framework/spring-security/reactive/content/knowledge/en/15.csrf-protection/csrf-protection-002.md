# Distinguishing CSRF, XSS, and CORS in Reactive Applications

## 1. Three concepts often confused as one

In Spring Security reactive applications (Spring WebFlux), **CSRF**, **XSS**, and **CORS** all relate to browsers, HTTP requests, and trust boundaries. However, they are **not three names for the same vulnerability**, nor can enabling one feature solve all three.

- **CSRF — Cross-Site Request Forgery:** an attacker causes the victim's browser to send **a state-changing request** to a system where the victim is logged in, abusing credentials that the browser auto-sends (usually a session cookie). The goal is to **perform an unintended action**, not necessarily to read the response.
- **XSS — Cross-Site Scripting:** untrusted data is inserted improperly into an HTML/JavaScript/DOM context, causing **attacker scripts to execute within the application's origin**. Goals may include reading displayed data, manipulating the DOM, sending requests on the victim's behalf, or stealing readable tokens.
- **CORS — Cross-Origin Resource Sharing:** a **browser policy mechanism** allowing a server to declare how other origins may use JavaScript to read responses and send certain cross-origin requests. **CORS is not an authentication engine, not an authorization mechanism, and not a CSRF solution.**

Three distinct questions:

| Question | Tool/Concept |
| --- | --- |
| Is someone trying to make a logged-in user's browser send an unauthorized action? | **CSRF**; mitigated with CSRF tokens, SameSite, origin checks, and proper request structure |
| Is any user data being interpreted as executable code inside the page? | **XSS**; mitigated with context-aware output encoding, safe DOM APIs, HTML sanitization, and supporting CSP |
| Should scripts at `https://app.example` be allowed to read responses from `https://api.example`? | **SOP/CORS**; handled via origin allowlists, methods, headers, and credentials policy |

### Learning Objectives

After this lesson, you will be able to:
1. Explain the threat models and differences among CSRF, XSS, CORS, SOP, and SameSite.
2. State why **disabling CORS does not eliminate CSRF**, and **enabling CORS does not inherently cause XSS**.
3. Distinguish browser auto-sent cookies from Bearer tokens explicitly attached in headers by the application.
4. Understand `CsrfWebFilter`, `ServerCsrfTokenRepository`, `ServerHttpSecurity.csrf(...)`, and CORS preflight ordering in Spring Security WebFlux.
5. Configure CORS with an explicit allowlist without arbitrarily reflecting every origin with credentials.
6. Prevent XSS on the server/frontend using DTOs, content types, context-aware encoding, and safe DOM APIs.
7. Build a Java 17+ Spring Boot WebFlux example with CORS, login sessions, and CSRF enabled; write `WebTestClient` tests for preflight, CSRF, and XSS data handling.
8. Design secure cross-origin APIs/SPAs and accurately diagnose 401/403/redirect/CORS errors.

## 2. The big picture

~~~text
                        Victim's browser
             ┌──────────────────────────────────┐
             │ Origin A: https://app.example     │
             │                                  │
             │ HTML / JavaScript / cookies      │
             └────────────┬─────────────────────┘
                          │
             ┌────────────┴─────────────┐
             ▼                          ▼
      Request from               Origin B script
      attacker's page            wants to call API A
      (cross-site)               and read response
             │                          │
             ▼                          ▼
   CSRF is dangerous if       SOP restricts by default;
   browser auto-sends cookie  CORS may relax rules for
   and server fails to        reading response/request types
   verify action intent       when server allows
             │                          │
             └────────────┬─────────────┘
                          ▼
             WebFlux/Spring Security backend
               CsrfWebFilter, CorsWebFilter,
               authN/authZ, controller
                          │
                          ▼
                      Response
                          │
         Is untrusted data inserted into
         HTML or DOM via innerHTML?
                          │
                  Yes -> XSS risk
                  No + proper encoding -> mitigates XSS
~~~

**Note:** XSS can arise from response data, server-rendered HTML pages, or JS reading JSON and inserting it into the DOM. Returning JSON with status 200 and the proper content type **does not automatically make the frontend safe** if the frontend later uses an unsafe sink.

## 3. CSRF: abusing the browser's request-sending authority

### 3.1. Basic scenario

A victim is logged into `https://bank.example` and holds a session cookie. They open another page controlled by an attacker. The attacker's page submits a POST form to `https://bank.example/transfer`. When cookie policy permits, the browser **may automatically attach `bank.example`'s cookie** to the request sent to `bank.example`.

If the server only checks "is there a valid session cookie?" without verifying that the request has a valid origin/intent, the money transfer may execute without the victim initiating it.

~~~text
Victim is logged into bank.example
         │
         ▼
Opens attacker.example
         │
         ▼
HTML form or request from attacker's page
         │
         ▼
POST https://bank.example/transfer
  Browser may attach session cookie, per SameSite/cookie policy
         │
         ▼
Server only verifies user is logged in
         │
         ▼
Unintended state change: CSRF
~~~

Key points:
- The attacker **does not have to read the response** to cause harm. Therefore, a CORS policy blocking response reads **does not prevent all CSRF**.
- The browser only auto-sends cookies under conditions governed by `SameSite`, domain, path, Secure, navigation/request type, and browser policies. Not every cross-site POST is guaranteed to carry cookies.
- If an HTTP GET mutates state (deleting records, placing orders, dangerous logout), GET requests can be exploited in many contexts where token policies usually **do not check**. **GET/HEAD/OPTIONS/TRACE must be safe methods: never perform business state mutations.**
- CSRF can also occur in HTTP Basic or mTLS environments if the browser auto-attaches credentials; it is not limited to session cookies.

### 3.2. Anti-CSRF measures

For browser applications using sessions/cookies:
1. **Unpredictable CSRF token bound to the user's session or secret**; the server validates the token on state-changing requests.
2. Appropriate **SameSite cookies** to reduce automatic cookie sending cross-site; this is an added defense layer, not a replacement for tokens across all models.
3. Verify **Origin/Referer** or Fetch Metadata headers such as `Sec-Fetch-Site` where appropriate; this supports a well-defined threat model rather than blindly trusting inconsistent headers across clients/proxies.
4. Never use GET to modify or delete data.
5. Ensure APIs enforce proper authentication/authorization, protect sensitive actions, and add re-verification when needed.
6. Test that missing/invalid tokens are rejected, and valid tokens lacking authorization are still rejected.

In Spring Security WebFlux, CSRF protection **is enabled by default** when using WebFlux security configuration, unless explicitly disabled. Thus, a POST without a token can receive **403 Forbidden** before reaching the controller or authentication manager.

### 3.3. How are CSRF tokens sent?

With a server-rendered HTML form, the form typically includes a hidden input:

~~~html
<form method="post" action="/api/notes">
  <input type="hidden" name="_csrf" value="TOKEN_FROM_SERVER" />
  <input name="text" />
  <button type="submit">Save</button>
</form>
~~~

**This HTML illustrates structure only; `TOKEN_FROM_SERVER` is not a real token and is not runnable.** The server must render the token generated by Spring Security for the active session, never hardcode a shared token or reuse one from another session.

For JavaScript POSTs, the application can send the token in the header expected by the server (usually `X-CSRF-TOKEN` or `X-XSRF-TOKEN` depending on `CsrfTokenRepository` / configuration). Identify the actual **repository, header name, and request handler** rather than copying a header from another example and expecting every setup to accept it.

Spring Security 6.x also processes tokens to mitigate BREACH risk when embedded in HTML. The displayed token may differ from the representation stored in the repository, so do not guess tokens by comparing a cookie string manually.

## 4. XSS: data interpreted as code in a trusted origin

### 4.1. Where does XSS happen?

Suppose an application accepts a username and returns JSON:

~~~json
{
  "displayName": "<img src=x onerror=alert(1)>"
}
~~~

This data **does not by itself execute script** when the browser receives JSON with a standard content type. The problem arises if the frontend feeds that string into an HTML parser:

~~~javascript
// WRONG: turns untrusted data into executable HTML.
displayNode.innerHTML = data.displayName;

// RIGHT when the goal is strictly displaying text:
displayNode.textContent = data.displayName;
~~~

When `innerHTML` receives a string containing markup, the browser can create dangerous elements/event handlers. `textContent` renders the data as plain text rather than HTML.

**XSS does not necessarily require `<script>` tags.** Event handlers, URL schemes, template injections, or other sinks can also execute code if context is uncontrolled.

### 4.2. Types of XSS

- **Reflected XSS:** request parameters are improperly echoed directly into the HTML response.
- **Stored XSS:** dangerous data is stored in a database/comment/profile and later displayed to other users.
- **DOM-based XSS:** client-side JavaScript passes untrusted data (URL fragments, postMessage, JSON responses...) into a dangerous DOM sink such as `innerHTML`, `insertAdjacentHTML`, or dynamic JS evaluation.

A WebFlux API might return completely normal JSON DTOs while the application UI still suffers from DOM XSS if unsafe rendering APIs are used. Conversely, a server-rendered Thymeleaf page can be safe when using **escaped text expressions** and unsafe when rendering raw/unescaped user HTML without sanitization.

### 4.3. How to protect

1. **Context-aware output encoding**: HTML body, HTML attributes, JavaScript strings, URLs, and CSS each have different rules; never rely on a single "escape everything" function everywhere.
2. **Prefer safe DOM APIs** such as `textContent`, `createTextNode`, and typed property assignment instead of HTML string concatenation.
3. If the product must allow rich HTML, use a **maintained HTML sanitizer with an appropriate policy**; do not roll your own simple regex filter.
4. With template engines, use **default escaping**. Never use raw HTML expressions for user data unless properly sanitized for that purpose.
5. Restrict content via business validation, but **input validation does not replace output encoding**: a string valid in one API can still be dangerous in another HTML context.
6. Use **Content Security Policy (CSP)** as defense-in-depth: restrict script sources, inline scripts, object sources, and exfiltration targets. CSP does not replace fixing XSS at the sink.
7. Minimize client-side token exposure; avoid storing session IDs/credentials in HTML or logs; use proper cookie flags while understanding that same-origin XSS can still **send requests on the user's behalf**, even when `HttpOnly` cookies cannot be read directly by JavaScript.

### 4.4. How can XSS break CSRF protection?

CSRF tokens defend against attackers **on external origins** because an external page normally cannot read the application's secret token (thanks to SOP and token design). If an attacker achieves XSS **executing inside the application's own origin**, their script can read the DOM containing the token and issue same-origin requests carrying the victim's cookies. Therefore:

> CSRF protection does not replace XSS protection; successful XSS can bypass many same-origin CSRF barriers.

Do not disable CSRF because of this. **Both are required**: CSRF blocks forged requests from other origins; output encoding/sanitization/CSP stop attackers from executing scripts in your own origin.

## 5. SOP and CORS: who may read responses cross-origin?

### 5.1. Origin consists of scheme + host + port

Examples:

| URL | Compared to `https://app.example` |
| --- | --- |
| `https://app.example/profile` | Same-origin |
| `https://api.example/profile` | Cross-origin (different host) |
| `http://app.example/profile` | Cross-origin (different scheme) |
| `https://app.example:8443/profile` | Cross-origin (different port) |

**Same-Origin Policy (SOP)** is the browser's security default: scripts at origin A are restricted from reading data from origin B. CORS is how server B declares which cross-origin response reads are permitted. Do not equate **origin** with **site** in SameSite cookies: "site" uses scheme/registrable domain scope, whereas origin also includes port.

### 5.2. CORS response headers

A server may respond with:

~~~http
Access-Control-Allow-Origin: https://app.example
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Meaning:
- `Access-Control-Allow-Origin` indicates which JS origin is permitted to access the response under CORS.
- `Access-Control-Allow-Credentials: true` informs the browser that cross-origin responses may be exposed when the client uses the appropriate credentials mode, **for a specifically named origin**.
- Never use `Access-Control-Allow-Origin: *` with credentialed responses. Browsers disallow wildcards when credentials are included.
- With an origin list, the server must select an allowed origin and emit the matching header, rather than reflecting arbitrary Origins alongside `Allow-Credentials: true`.
- `Vary: Origin` is critical when caching responses that vary by Origin to avoid policy cache poisoning.

### 5.3. What does a preflight OPTIONS request mean?

For certain cross-origin requests, such as JSON POSTs with `Content-Type: application/json` or requests with custom headers, the browser sends a **preflight**:

~~~http
OPTIONS /api/notes HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

The server responds allowing it if the origin/method/headers match its policy:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Allow-Credentials: true
~~~

After a valid preflight, the browser sends the actual request in preflighted cases. **Preflight does not prove the user is authorized or holds a CSRF token.** It only indicates the browser is allowed to attempt the request under CORS policy. Authentication, CSRF, and authorization are still checked separately on the main request.

Preflights typically do not carry cookies/sessions. If a CORS filter runs after a rule requiring login, OPTIONS may incorrectly return 401/302/403. With Spring Security WebFlux, integrate CORS so it is processed **before** authentication/authorization as appropriate.

### 5.4. Why does disabling CORS not prevent CSRF?

**Simple requests**, especially standard HTML forms from another origin, can be sent by the browser without a preflight. If the server returns a response without CORS headers, the attacker's JavaScript cannot read the response; that **does not undo the POST mutation already executed by the backend**.

Table:

| Scenario | What does CORS help with? | What does CSRF need? |
| --- | --- | --- |
| Form POST from another site | Does not block simple form submissions | Tokens/Origin/SameSite and safe-method discipline |
| Cross-origin JSON fetch | CORS policy may require preflight and govern response exposure | If auto-sending cookies/session, still needs CSRF defense per threat model |
| Script on the app's own origin | CORS does not apply to same-origin requests | XSS can read tokens from DOM; requires XSS defense |
| Server-to-server request via curl | CORS is not a firewall; curl can call any URL | Authentication, authorization, and server-side controls |
| User accessing another user's profile by ID | Does not solve IDOR | Object authorization/owner/tenant checks |

Never rely on CORS as a mechanism to block untrusted clients. Any non-browser client can spoof `Origin` or omit Origin altogether. The backend must always authenticate and authorize.

## 6. Cookies, SameSite, CSRF tokens, and Bearer tokens

### 6.1. Session cookies are sent automatically

Browsers automatically decide whether to send cookies based on domain/path, Secure, SameSite, and policies. Browser apps using session-based login must treat certain cross-site requests as potentially impactful if cookies are sent.

- `HttpOnly` prevents JavaScript from reading the cookie directly; it **does not stop** the browser from attaching the cookie to requests.
- `Secure` requires cookies over HTTPS (with some local behavior exceptions).
- `SameSite=Lax` reduces cookie sending on many cross-site subrequests, but is not an absolute shield against all CSRF or state-changing GETs. SameSite is also not synonymous with SOP/CORS.
- `SameSite=Strict` further restricts cross-site cookies but can affect navigation/login flows; evaluate product impact.
- `SameSite=None; Secure` is often needed for genuine cross-site cookie models; therefore **never rely solely on SameSite**.

### 6.2. Bearer tokens explicitly attached by JavaScript

If an API uses OAuth2 Bearer tokens in the `Authorization: Bearer ...` header where **the browser does not auto-attach** these credentials on cross-site requests from an attacker page, classic CSRF risk differs significantly from cookies. However:
- XSS on the application's own page can steal/access tokens depending on storage and send requests on the user's behalf.
- If the application **still uses cookies** for refresh tokens/sessions or other endpoints, those endpoints may still need CSRF protection.
- HTTP Basic and client certificates can act as ambient browser credentials; do not infer "API = no CSRF needed".
- Do not disable CSRF globally just because one endpoint accepts Bearer tokens; separate security chains and inspect credential delivery per route group.

### 6.3. Cross-origin SPAs need three independent configuration layers

Example:
- Frontend: `http://localhost:5173`.
- Backend: `http://localhost:8080`.
- Backend uses session cookies, not Bearer-only.

For the frontend to call APIs with credentials:
1. **CORS allowlist** must name the exact frontend origin; if cookies are used, enable allow-credentials and avoid wildcard origins.
2. Client `fetch` must configure `credentials: "include"` (along with matching headers/body). CORS allows responses to be read when browser conditions are met.
3. **CSRF token** must be securely obtained by the frontend through a backend-designed mechanism, then sent in a header for POST/PUT/PATCH/DELETE requests. Simply enabling CORS and credentials does not supply a CSRF token.
4. Cookie SameSite/Secure/path/domain must fit. Cross-origin is not necessarily cross-site; two origins with different ports on the same hostname can still be same-site in browser models.
5. The server still validates authentication, authorization, CSRF tokens, and input.

Illustrative JS snippet when the frontend **already holds a valid token** (token issuance must be built separately):

~~~javascript
async function createNote(text, csrfToken) {
  const response = await fetch("http://localhost:8080/api/notes", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": csrfToken
    },
    body: JSON.stringify({ text })
  });

  if (response.status === 401) {
    throw new Error("Re-authentication required");
  }
  if (response.status === 403) {
    throw new Error("Forbidden: access denied or CSRF");
  }
  if (!response.ok) {
    throw new Error("Request failed");
  }
  return response.json();
}
~~~

**Non-standalone snippet:** it assumes the user is already logged in with a valid cookie and the CSRF token was obtained by the frontend in a manner matching the repository/handler. The runnable Java demo below **does not yet implement a dedicated CSRF-token-issuing endpoint for SPAs**, because the goal is cleanly separating CORS and CSRF; it uses the default login page and Spring Security Test to verify CSRF.

## 7. Spring Security WebFlux: related components

| Component | Role |
| --- | --- |
| `ServerHttpSecurity` | DSL for configuring the WebFlux security chain |
| `SecurityWebFilterChain` | WebFilter chain processing security requests |
| `CsrfWebFilter` | Validates CSRF on protected requests |
| `ServerCsrfTokenRepository` | Saves/loads/generates CSRF tokens per policy |
| `WebSessionServerCsrfTokenRepository` | Session-based repository used in standard WebFlux CSRF configurations |
| `CookieServerCsrfTokenRepository` | Cookie-based repository option (commonly for SPA scenarios); requires understanding HttpOnly and request handlers |
| `CorsWebFilter` / `ServerHttpSecurity.cors(...)` | Handles CORS/preflight per configuration source |
| `CorsConfigurationSource` | Configures origins, methods, headers, credentials... |
| `AuthenticationWebFilter` | Attempts to authenticate credentials on matching requests |
| `AuthorizationWebFilter` | Enforces `authorizeExchange` rules by identity/authorities |
| `ReactiveSecurityContextHolder` | Accesses SecurityContext via Reactor Context |

### 7.1. CSRF enabled by default; exceptions require justification

Configuration snippet:

~~~java
return http
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/public").permitAll()
        .anyExchange().authenticated()
    )
    .formLogin(Customizer.withDefaults())
    .build();
~~~

Spring Security WebFlux enables CSRF protection by default for HTTP methods outside the safe group. Never add `.csrf(csrf -> csrf.disable())` just to allow client POSTs without tokens.

If the app has a webhook/token endpoint needing an exemption, design a **specific scope**, authenticate it independently via signatures/appropriate headers, and test that other session-cookie routes still require CSRF. Matcher scopes must be reviewed; do not confuse CSRF exemptions with `permitAll`.

### 7.2. CORS runs before security authentication

Preflight `OPTIONS` requests usually lack session cookies; if the pipeline requires login before handling CORS, browsers report preflight errors. Integrating CORS into `ServerHttpSecurity` ensures CORS runs in the right order within WebFlux.

When configuring:
- Allowlist origins with exact scheme + hostname + port.
- Permit only the methods and headers the frontend needs.
- Enable `allowCredentials(true)` **only when** the backend genuinely supports cross-origin cookie/credential requests and origins are controlled.
- Never arbitrarily reflect any origin or combine wildcard origins with allow-credentials.
- Test both permitted and rejected preflights, especially on endpoints requiring login.

### 7.3. CORS does not replace HTTP authorization

Suppose the frontend is allowed to call `POST /api/notes`. The user must still be authenticated, carry a valid CSRF token if using session cookies, and hold the required authority if the API enforces special roles. Requests from an allowlisted origin **do not** gain permission to bypass `authorizeExchange` or object-level authorization.

CORS also does not stop Postman/curl/server-to-server callers from hitting the API. Every critical access control must live on the server, never relying on the browser.

## 8. Runnable Java 17+ example: WebFlux with CSRF and CORS

The project uses Spring Boot **3.3.13**, Java 17+, and Gradle 8.x. Versions are pinned so the lesson targets consistent APIs; production apps must use supported versions, upgrade dependencies, and re-test.

Example behavior:
- `GET /api/public?name=...` open to anonymous users, returns JSON; `name` may contain markup, but the API does not render HTML.
- `GET /account` requires session login; Spring Security generates `/login` and handles the form.
- `POST /api/notes` requires login and a **valid CSRF token**; returns JSON 201 Created.
- CORS only allows `http://localhost:5173` to call `/api/**` with GET, POST, and specific headers.
- Does not disable CSRF.
- Tests preflight, XSS boundary, POST with/without CSRF, and that CORS grants no authentication.

### 8.1. Project structure

~~~text
webflux-csrf-xss-cors/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── BrowserSecurityApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/
        └── BrowserSecurityTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-csrf-xss-cors'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

- Spring Boot manages compatible Spring Security and Reactor versions via dependency management.
- Do not add `spring-boot-starter-web` (Servlet MVC) since the target is reactive WebFlux.
- `spring-security-test` supplies test configurers like `mockUser()` and `csrf()`, never to be used to grant fake privileges in production.

### 8.2. Bootstrap class

`src/main/java/demo/BrowserSecurityApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BrowserSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(BrowserSecurityApplication.class, args);
    }
}
~~~

### 8.3. Spring Security WebFlux, CSRF, and CORS configuration

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(reader);
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration policy = new CorsConfiguration();

        // Exact scheme + host + PORT of the test frontend.
        policy.setAllowedOrigins(List.of("http://localhost:5173"));
        policy.setAllowedMethods(List.of("GET", "POST"));
        policy.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
        policy.setAllowCredentials(true);
        policy.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", policy);
        return source;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http, CorsConfigurationSource corsSource) {

        return http
            // CORS before authN for OPTIONS preflight.
            .cors(cors -> cors.configurationSource(corsSource))

            // DO NOT disable CSRF. Protects POST/PUT/DELETE by default.
            .csrf(Customizer.withDefaults())

            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/account", "/api/notes").authenticated()
                .anyExchange().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            // Browser demo uses form login, HTTP Basic not needed.
            .httpBasic(basic -> basic.disable())
            .build();
    }
}
~~~

**Key points to understand:**
1. `CorsConfigurationSource` uses the reactive API in `org.springframework.web.cors.reactive`; do not mistakenly copy Servlet MVC configuration.
2. `http.cors(...)` integrates CORS into Spring Security WebFlux. Valid OPTIONS preflights can be answered without requiring an authenticated session.
3. Only `http://localhost:5173` is allowlisted. Other origins like `https://malicious.example` are not granted access. `AllowCredentials(true)` **does not** mean every browser auto-attaches cookies; browsers still obey cookie/SameSite policies and client credentials mode.
4. We register CORS only for `/api/**`. `/login` and `/account` are HTML navigations and do not need CORS for scripts from other origins.
5. `csrf(Customizer.withDefaults())` shows CSRF remains enabled. Default WebFlux session-based login pairs cleanly with the CSRF session repository.
6. `.formLogin(...)` enables the generated login page at `GET /login` and handles `POST /login` (with CSRF token).
7. `authorizeExchange` protects `/account` and `/api/notes` with authentication; CORS grants no permissions to anonymous callers.
8. The demo password is BCrypt-hashed; `reader-pass` is strictly for local samples and must never reach production.
9. For a real frontend using cross-origin cookies/sessions, an appropriate CSRF-token-issuing flow must be added. This CORS policy is only **one piece**, not a complete SPA login application.

### 8.4. Controller: distinguishing JSON data from executable HTML

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
class DemoController {

    public record Greeting(String greeting) {}
    public record NoteInput(String text) {}
    public record NoteView(String text) {}

    // Returns JSON only; NEVER concatenate name directly into an HTML page.
    @GetMapping("/api/public")
    Mono<Greeting> hello(
            @RequestParam(defaultValue = "guest") String name) {
        return Mono.just(new Greeting("Hello, " + name));
    }

    @GetMapping("/account")
    Mono<String> account() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx ->
                Mono.justOrEmpty(ctx.getAuthentication()))
            .map(Authentication::getName)
            .map(name -> "Hello " + name);
    }

    // State-changing endpoint: requires session auth and CSRF.
    // Demo returns new data without persisting long-term to a database.
    @PostMapping("/api/notes")
    Mono<ResponseEntity<NoteView>> create(
            @RequestBody Mono<NoteInput> request) {

        return request.map(input -> {
            if (input.text() == null
                || input.text().isBlank()
                || input.text().length() > 200) {

                throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid note text");
            }

            return ResponseEntity.status(HttpStatus.CREATED)
                .body(new NoteView(input.text()));
        });
    }
}
~~~

The controller intentionally:
- Omits `@PostMapping("/login")` because standard form login is handled by security filters.
- Does not trust `origin` or CORS to grant identity/permissions.
- Does not concatenate user input into an HTML response. `Greeting` is JSON data: the frontend must render it with `textContent`, not `innerHTML`.
- Does not return raw passwords, cookies, SecurityContext, or tokens.
- `POST /api/notes` requires both authentication and a CSRF token. If CSRF fails, the controller is not invoked, even with valid note text.
- Length validation is useful but **does not replace** escaping when data is displayed in HTML.
- Note data is not persisted; the project illustrates the security pipeline, not production persistence.

### 8.5. Try in a browser

Run in the project directory with Java 17+ and Gradle 8.x:

~~~bash
gradle bootRun
~~~

If using Gradle Wrapper, run `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows). The server defaults to `http://localhost:8080`.

Try:
1. Open `http://localhost:8080/api/public?name=reader` -> JSON `{"greeting":"Hello, reader"}`, no login required.
2. Open `http://localhost:8080/account` while unauthenticated -> per the form-login entry point, typically redirects to `/login`.
3. `/login` is generated by Spring Security; sign in with `reader` / `reader-pass`. The default form already integrates the CSRF token.
4. Re-open `/account` in the same session -> body `Hello reader`.
5. For an actual POST to `/api/notes`, the browser must send a JSON body (or accepted media type), a valid session cookie, **and a valid CSRF token**; omitting CSRF yields 403.
6. When the `http://localhost:5173` frontend runs, preflight `OPTIONS /api/notes` with POST/Content-Type is accepted by the allowlist. However, an allowlisted origin **does not** make `POST /api/notes` succeed if the user is not logged in or lacks the token.

**Note:** HTTP demo URLs are local-only. For cross-site production browsers, cookie settings (Secure/SameSite) and CORS policy must align with HTTPS and the threat model; avoid open configurations across all origins.

## 9. Automated testing with `WebTestClient`

Spring Security Test for reactive WebFlux provides:
- `springSecurity()`: attaches security filters to the mock WebTestClient bound to ApplicationContext.
- `mockUser()`: creates a mock user **only in tests** to verify other security layers; does not prove real password login flows.
- `csrf()`: sends a valid CSRF token **only in test scope**, does not disable production CSRF.
- OPTIONS requests to test CORS preflight along with Origin/method/headers.

`src/test/java/demo/BrowserSecurityTests.java`:

~~~java
package demo;

import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class BrowserSecurityTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicJsonIsAvailableWithoutLoginOrCsrf() {
        client.get().uri("/api/public?name=reader")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.greeting").isEqualTo("Hello, reader");
    }

    @Test
    void loginPageIsAvailableForBrowserSessionLogin() {
        client.get().uri("/login")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_HTML);
    }

    @Test
    void authenticatedUserStillNeedsCsrfForPost() {
        client.mutateWith(mockUser("reader"))
            .post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "draft"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validCsrfAllowsAuthenticatedPost() {
        client.mutateWith(mockUser("reader"))
            .mutateWith(csrf())
            .post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "draft"))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.text").isEqualTo("draft");
    }

    @Test
    void allowedOriginPreflightPassesWithoutLoginCookie() {
        client.options().uri("/api/notes")
            .header(HttpHeaders.ORIGIN, "http://localhost:5173")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "content-type")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "http://localhost:5173");
    }

    @Test
    void unknownOriginPreflightIsRejected() {
        client.options().uri("/api/notes")
            .header(HttpHeaders.ORIGIN, "https://unknown.example")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "content-type")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void allowedOriginCannotBypassCsrf() {
        client.mutateWith(mockUser("reader"))
            .post().uri("/api/notes")
            .header(HttpHeaders.ORIGIN, "http://localhost:5173")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "change"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void xssLookingInputRemainsJsonDataNotHtmlResponse() {
        String input = "<img src=x onerror=alert(1)>";

        client.get().uri(uriBuilder -> uriBuilder
                .path("/api/public")
                .queryParam("name", input)
                .build())
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.greeting").isEqualTo("Hello, " + input);
    }
}
~~~

The tests are written to run against the WebFlux mock server. The eight scenarios above illustrate:

1. Public GET requires no CSRF and returns JSON.
2. Default login page is accessible.
3. **Even when authenticated**, a POST missing the token is rejected 403 by the CSRF filter.
4. Valid mock user and token allow the POST to reach the controller and return 201.
5. CORS preflight from an allowed origin is processed **before auth**, requiring no session cookie.
6. Preflight from an unknown origin is rejected.
7. An allowlisted origin **does not** replace CSRF tokens: POST still returns 403.
8. An HTML-script-like string is returned as JSON data, not an executable HTML response. **This test does not prove the entire frontend is XSS-safe**: the UI must render using safe DOM APIs.

Run:

~~~bash
gradle test
~~~

Or the corresponding wrapper if present. Eight tests are expected to pass with compatible dependencies; compile and run in your project environment to confirm in practice. Do not treat mock users as proof that password/BCrypt login was tested; for real systems, add integration tests with session login and real CSRF tokens.

### 9.1. Mandatory test matrix for production applications

| Request | Expectation |
| --- | --- |
| Public GET without cookies | 200 if `permitAll` rule |
| State-changing POST with real session but no CSRF | 403 |
| POST with forged/wrong-session CSRF | 403 |
| POST with valid CSRF but anonymous user | 401 or login redirect per entry point |
| POST with valid CSRF but missing role | 403 |
| POST with valid CSRF and valid authority | 2xx per contract |
| Allowlisted CORS preflight | Returns matching origin/method/headers; not blocked by login |
| Disallowed-origin CORS preflight | Does not expose access via CORS (typically 403) |
| Disallowed-method/header CORS preflight | Rejected by CORS policy |
| Public GET with malicious HTML string | JSON is data; frontend avoids unsafe sinks |
| Inserting data into HTML text/attribute/URL | Context-aware encoding, real UI XSS tests |
| API targeting another user's resource | Authorization/ownership blocks regardless of Origin |
| POST with browser HTTP Basic/cookie | Properly evaluate CSRF threat model |
| GET causing data mutation | Incorrect design; move to protected unsafe method |

## 10. When is CSRF disabled in stateless APIs?

The answer is not "every REST API must disable CSRF". Examine **how credentials reach the backend**.

### Cases where omitting CSRF tokens is typically justified

An API using exclusively Bearer tokens where the client explicitly attaches `Authorization: Bearer ...` and **no ambient credentials** are auto-sent by browsers—no session cookies, remember-me cookies, Basic auth, or client certificates are used for authentication on those endpoints. In that case, an attacker on another origin generally cannot make the browser auto-send the victim's Bearer token via a plain HTML form.

However, you must verify:
- Can tokens leak to external origins or via XSS?
- Are there refresh/session/cookie endpoints using ambient credentials?
- Does permissive CORS + exposed token/credential flow create other risks?
- Does the API validate issuer, audience, expiration, scopes, and object-level authorization?
- If the same domain serves both session UI and Bearer APIs, are separate CSRF rules per chain/matcher accurate?

### Cases where CSRF is still required

- WebFlux form login using session cookies.
- Browsers calling APIs with session cookies.
- HTTP Basic in browsers where the browser may resend cached credentials.
- Refresh-token cookies or endpoints using auto-attached credentials.
- Any state-changing endpoint accepting ambient browser authentication.

**Common mistake:**

~~~java
// Dangerous if the application still authenticates via cookies/sessions.
http.csrf(csrf -> csrf.disable());
~~~

The snippet above illustrates an **anti-pattern** and does not appear in the runnable configuration of this lesson. If you must exempt a webhook or Bearer-only endpoint, prefer clearly partitioned paths/security chains with dedicated policies; never disable CSRF globally just to make one POST work.

## 11. Real-world troubleshooting scenarios

### 11.1. Browser reports "CORS policy blocked" when frontend calls API

Check in order:
1. Identify the exact **Origin** including scheme, host, and port.
2. Check whether an OPTIONS preflight occurred and what status the server returned.
3. If there was a preflight, verify `Access-Control-Request-Method` and `Access-Control-Request-Headers` are allowlisted.
4. Verify the server returns `Access-Control-Allow-Origin` matching the **exact origin**; `*` cannot be used for credentialed responses.
5. With credentials, check `Access-Control-Allow-Credentials`, JS `credentials: "include"`, cookie SameSite/Secure, path/domain.
6. Ensure the CORS filter runs before authentication: OPTIONS usually lacks cookies.
7. Check whether a proxy/CDN strips CORS headers or caches incorrectly without `Vary: Origin`.
8. When OPTIONS passes yet the actual POST returns 403, inspect **CSRF, authentication, and permissions**; do not tweak CORS blindly.

### 11.2. POST returns 403 even though user is logged in

Distinguish:
- **CSRF 403:** missing/invalid token on an unsafe method, token not bound to the right session or request handler.
- **Authorization 403:** authenticated, but lacking authority/owner/tenant permission.
- **CORS 403:** preflight/actual CORS request from a disallowed origin/method/header, potentially rejected by CorsWebFilter.
- **Other error:** another security filter/proxy/policy returned 403.

Log sanitized details (request ID, error category, method, policy rule) without logging session cookies, CSRF tokens, or Authorization headers. Do not equate every 403 with a single cause.

### 11.3. Is a GET JSON containing `<img ...>` already XSS?

You cannot conclude from JSON alone. If the backend returns `Content-Type: application/json` and the frontend uses `textContent`, the string remains plain text. If the frontend inserts it into `innerHTML`, raw template output, or an HTML/JS decoding sink, XSS can happen.

Tests must cover **the point where data enters the DOM** or actual HTML views, not just the JSON serializer. Add CSP and sanitizers wherever user-generated HTML is required.

### 11.4. SPA login has a cookie yet API still returns 401

Potential causes include:
- Cookie was not sent due to SameSite, Secure, path, domain, or missing `credentials: "include"`.
- Session expired or was not persisted on the server.
- CORS policy rejected the response (browser console reports CORS while the server may have sent another status).
- Entry point redirected to HTML, causing `fetch` to follow and the frontend to fail parsing HTML as JSON.
- Cross-site cookies blocked by browser policies despite backend `Allow-Credentials`.

Design a clear HTTP contract: HTML navigations can redirect to login; JSON APIs should have an appropriate 401 authentication entry point instead of returning HTML to clients expecting JSON. CORS policy does not replace building a 401 contract.

## 12. Quick comparison to avoid confusion

| Aspect | CSRF | XSS | CORS |
| --- | --- | --- | --- |
| What is it? | Attack class forging unauthorized actions | Attack class executing content/scripts inside an origin | Browser mechanism permitting cross-origin access by policy |
| Attacker goal | Submit unintended actions as victim | Run code within victim's origin | CORS misconfiguration may let external origin scripts read data |
| Typical conditions | Browser auto-sends credentials; missing intent/token check | Untrusted input reaches dangerous HTML/JS/DOM sink | Server misconfigures or overly broadens origin/method/header/credentials |
| Need to read response? | **No** | Can read same-origin data if XSS executes | Cross-origin response reading is central to CORS/SOP |
| Primary defenses | CSRF tokens, SameSite, origin checks, safe methods | Contextual escaping, safe DOM, sanitizer, supporting CSP | Origin allowlists, preflight handling, credential policy |
| Spring Security WebFlux | `CsrfWebFilter`, `ServerCsrfTokenRepository` | Supporting headers/CSP; encoding mainly in templates/UI | `CorsWebFilter`/`ServerHttpSecurity.cors` |
| If user is not logged in? | CSRF can still threaten via login CSRF or auto-sent credentials | XSS can still occur on public pages | CORS applies to anonymous requests too |
| Does disabling CORS solve it? | **No** | **No** | Stops cross-origin JS reading responses unless otherwise permitted |
| Does a CSRF token solve XSS? | No | **No**; same-origin XSS can read tokens | Not directly related |

## 13. Common mistakes and fixes

| Mistake | Why dangerous/wrong | How to fix |
| --- | --- | --- |
| "CORS is off so we don't need CSRF" | Cross-site form POSTs can still be sent and mutate state | CSRF tokens and server-side policy for unsafe methods |
| "CORS allows this frontend so the frontend is authorized" | CORS is only a browser policy, does not authenticate users | Enforce AuthN, AuthZ, and CSRF independently |
| `allowedOrigins("*")` with `allowCredentials(true)` | Wildcard is incompatible with credentialed CORS; reflecting every origin is also dangerous | Allowlist specific minimal origins |
| Requiring login before OPTIONS preflight | OPTIONS lacks cookies and gets redirected/401 | Configure Spring Security CORS before auth |
| Using `permitAll` on POST thinking CSRF is skipped | Authorization does not disable `CsrfWebFilter` | Configure explicit CSRF matcher if justified, with tests |
| Disabling CSRF globally with form login/sessions | Opens the door to forged state-changing requests | Keep CSRF, render tokens via proper repository |
| Turning CSRF-protected POSTs into GETs for easy testing | GET side effects are easily forged and triggered by caches/crawlers | Keep unsafe methods and handle tokens |
| Hardcoding CSRF tokens in JS | Shared/predictable tokens fail to stop forgery | Issue session/secret-bound tokens from the server |
| Confusing cookie SameSite with CORS origin | Site and origin have different scopes; each policy solves a different problem | Design cookies/CORS/CSRF separately |
| Using `innerHTML` for API data | DOM XSS | Use `textContent` or sanitize HTML |
| Validating input with regex only without output escaping | Valid input in one context can execute in another render context | Context-aware encoding + safe DOM sinks |
| Returning only JSON so assuming frontend has no XSS | JS can still inject JSON into HTML | Test DOM end-to-end, avoid unsafe sinks |
| Relying on CSP instead of fixing XSS | CSP can have gaps/bypasses/misconfigurations | Fix output encoding; use CSP as defense-in-depth |
| Thinking `HttpOnly` prevents XSS from doing anything | Same-origin JS can still issue requests with auto-attached cookies | Stop XSS at the source; HttpOnly only blocks cookie reads |
| Logging form passwords/CSRF tokens/cookies for debugging | Secrets leak into logs | Log trace IDs and error types, never raw credentials |
| Treating every 403 as a CSRF failure | Could be CORS/authorization/ownership | Categorize by filter, method, preflight, policy |
| Calling `block()` to read tokens/security context in WebFlux | Blocks the event loop | Compose reactive publishers, return `Mono` |
| Not verifying CSRF tokens against the current session | Another session's token might be accepted improperly | Use standard `ServerCsrfTokenRepository` and test mismatches |
| Treating the Origin header as identity | Non-browser clients can spoof Origin | Authenticate user/tokens independently |
| Not testing preflight and actual requests separately | OPTIONS passes while POST fails or vice versa | Two-step testing separating CORS/CSRF/auth |

## 14. Practice exercises

**Q1.** An attacker cannot read the response due to CORS, yet the browser still submits a money-transfer POST with cookies and the server executes it. What vulnerability is this?

**Answer:** CSRF. Reading the response is unnecessary to cause impact; intent must be protected via CSRF tokens/origin checks and cookie policies.

**Q2.** A user profile page reads `{"name":"<img ...>"}` and assigns `element.innerHTML = name`. What is this?

**Answer:** DOM-based XSS (possibly stored/reflected depending on source). Use `textContent` when displaying plain text; if rich HTML is needed, use a proper sanitizer.

**Q3.** Frontend `http://localhost:5173` calls API `http://localhost:8080`. Why are they cross-origin?

**Answer:** Origin includes port; 5173 and 8080 differ even though both are localhost.

**Q4.** OPTIONS preflight carries no cookies, yet the API requires authentication on all routes. What should you do?

**Answer:** Configure CORS to process preflight before auth, restricting origins/methods/headers; the actual request must still be authenticated, authorized, and carry a CSRF token if needed.

**Q5.** Are `Access-Control-Allow-Origin: *` and `Access-Control-Allow-Credentials: true` valid together?

**Answer:** No. Browsers forbid wildcard origins on credentialed CORS responses; configuration must allowlist specific origins.

**Q6.** A request arrives from an allowlisted origin with a valid user session, but without a CSRF token. Will the POST succeed?

**Answer:** No under default WebFlux CSRF; unsafe POSTs undergo CSRF validation and usually return 403.

**Q7.** Does GET require a CSRF token by default?

**Answer:** Usually no, because GET must be a safe method. If GET causes side effects, fix the API design rather than expecting the CSRF filter to protect it.

**Q8.** Can HTTP Basic be vulnerable to CSRF?

**Answer:** Yes, if the browser auto-sends cached credentials in a cross-site context; base the assessment on credential delivery, not just API auth naming.

**Q9.** Does a stateless Bearer token manually attached by an SPA in the Authorization header carry the same CSRF risk as session cookies?

**Answer:** Not necessarily; ambient cookies differ from headers actively attached by JS. However, XSS and other refresh/cookie endpoints must still be reviewed.

**Q10.** Does `HttpOnly` stop XSS from performing requests with the user's privileges?

**Answer:** No. It prevents JS from reading the cookie directly, yet the browser still auto-sends cookies on same-origin requests. XSS must be blocked at rendering/DOM sinks.

**Q11.** Does CORS protect an endpoint from curl/Postman?

**Answer:** No. CORS is browser enforcement; the server must enforce authentication, authorization, and input validation.

**Q12.** Why is testing that JSON returns a `<script>` string insufficient to conclude the UI is safe?

**Answer:** JSON is just data; the risk emerges when the UI uses sinks like `innerHTML`. Test the actual rendering path.

**Q13.** A browser is redirected from an API to `/login`, causing `response.json()` to fail parsing. Is CORS definitely misconfigured?

**Answer:** No. The form-login entry point may be returning HTML/redirect because the request is unauthenticated. Design a JSON 401 API entry point when appropriate.

**Q14.** Can CSRF be disabled for a webhook verified with an HMAC signature?

**Answer:** You can design a clearly scoped exception for an endpoint that does not use ambient cookies, backed by signature verification, replay protection, and tests. Do not extend the exception to form login/session APIs.

**Q15.** CORS preflight returns OK, yet the actual POST returns 403. What should you check?

**Answer:** CSRF token matching the repository/session, authentication, permissions, cookies, and other filters. A successful OPTIONS only confirms CORS policy for that request type.

## 15. Secure implementation checklist

- [ ] Clearly distinguish CSRF, XSS, CORS, and SOP in design; never treat one layer as a substitute for another.
- [ ] Enable CSRF protection for flows using sessions/cookies/ambient credentials on unsafe methods.
- [ ] Server issues/validates CSRF tokens per configured session and request handler; test missing/invalid tokens.
- [ ] Zero GET endpoints mutating business state.
- [ ] CORS allowlist contains only genuinely needed origins, methods, and headers; preflight is not blocked by auth.
- [ ] Never use wildcard/reflected Origins + credentialed responses.
- [ ] Cookie `HttpOnly`, `Secure`, `SameSite`, path/domain are designed to fit browser flows.
- [ ] If a cross-origin SPA uses cookies, provide an explicit token-issuance contract for the frontend; do not assume CORS supplies tokens.
- [ ] Inputs use DTOs and validation; HTML outputs are context-encoded.
- [ ] Frontend DOM prefers `textContent` and avoids unsafe HTML sinks; rich HTML is sanitized.
- [ ] CSP deployed appropriately, without replacing XSS fixes; restricts scripts and exfiltration destinations.
- [ ] Authentication and HTTP/object authorization enforced on the backend, never relying on client-sent Origin/headers.
- [ ] API 401/403 and browser redirects have clear contracts, avoiding returning HTML to clients expecting JSON.
- [ ] Tests cover allowed/disallowed preflight, POST missing CSRF, POST with CSRF, missing auth, and missing roles.
- [ ] XSS tests target real DOM/template sinks, not only JSON payloads.
- [ ] Never log tokens, passwords, Authorization headers, session cookies, or sensitive data.
- [ ] Never call `block()` or manually `subscribe()` to access security context in WebFlux.
- [ ] Separate security configurations for stateless JWT, HTML form/session, and webhooks are clearly isolated and security-reviewed.

## 16. References

- Spring Security — WebFlux CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Reactive CORS: https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive CSRF tests: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Framework — WebFlux CORS: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- OWASP — CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP — XSS Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- MDN — Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS
- MDN — Same-Origin Policy: https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy

**Takeaway:** **CSRF** is forging actions via requests carrying victim credentials; **XSS** is executing code because untrusted data is rendered improperly; **CORS** is a browser mechanism governing cross-origin response access and preflights. With Spring Security reactive, configure **CSRF, CORS, authentication/authorization, and frontend output encoding as independent yet coordinated layers**. Never rely on CORS to prevent CSRF, and never rely on CSRF tokens to cure XSS.
