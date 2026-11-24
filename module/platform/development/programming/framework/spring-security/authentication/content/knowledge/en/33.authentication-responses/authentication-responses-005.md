# Distinguishing Unauthenticated Access from HTTP 403 Authorization Errors in Spring Security

## 1. Quick Answer: 401 Is Missing Valid Authentication, 403 Is Access Denied

Two fundamental questions in a web security system are:

1. **Authentication:** **Who** is the request from, and is the login proof/cookie/access token **valid**?
2. **Authorization:** Is that authenticated principal allowed to perform **this action on this resource**?

According to **RFC 9110**, HTTP **401 Unauthorized** means the request has not been applied because it **lacks valid authentication credentials** for the target resource; the name "Unauthorized" is historical, yet in practice it indicates an **authentication** issue. HTTP **403 Forbidden** means the server understood the request but **refuses to authorize it**, typically **authenticated yet lacking permissions**.

| State | Diagnostic Question | Typical HTTP in REST APIs | Appropriate Action |
| --- | --- | --- | --- |
| No credentials sent to login-required route | "Who are you?" | **401** with scheme's `WWW-Authenticate` | Log in / send valid credentials |
| Wrong username/password or bad Basic credential | "Does this proof authenticate?" | **401** for HTTP Basic; form login typically **302 to error page** | Fix credentials, do not guess roles |
| Bearer access token bad signature/expired/revoked | "Is there a valid token?" | **401**, Bearer `invalid_token` when appropriate | Obtain new token; fix issuer/audience config |
| Valid principal missing `ROLE_ADMIN` | "Logged in, allowed into admin?" | **403** | Request right permissions; do not loop login infinitely |
| Valid Bearer token lacking required API scope | "Sufficient scope for resource?" | **403**, Bearer `insufficient_scope` if policy and error handler know it is valid OAuth authentication | Request appropriate authorization/scope |
| Cookie-based POST missing/invalid CSRF token | "Trusted origin for state-changing request?" | **403**, **even when user is not logged in** | Obtain and send valid CSRF token; never disable CSRF |
| Browser Form Login not authenticated | "Which login UI should user go to?" | Usually **302 Location: /login**, **not necessarily 401** | Follow redirect; do not force 401 rigidly |
| Authenticated yet denied by business rule/tenant/ownership | "Owns resource or belongs to right tenant?" | **403**, sometimes 404 to avoid exposing resource existence per design | Do not treat as a password error |

**Two conclusions must go together:**

- In a properly configured **HTTP Basic/Bearer REST API**, **401** primarily means lacking valid authentication; **403** primarily means authenticated yet lacking permissions.
- **Never infer backward from 403 that the user is definitely authenticated**, nor from 302 that they are logged in. `CsrfFilter`, CORS, reverse proxies, WAFs, controllers, and custom `AuthenticationEntryPoint` implementations can also return 403/302 depending on configuration.

Learning objective: explain the flow of `AuthenticationException` and `AccessDeniedException` in Spring Security, the rationale behind HTTP 401/403/302, inspect Bearer `WWW-Authenticate`, write sound configurations, and write negative tests distinguishing real failure causes.

## 2. HTTP Semantics Under RFC 9110

### 2.1. 401 Unauthorized

An HTTP 401 response indicates that an appropriate **authentication challenge** is needed for the resource. Under RFC 9110, **a server generating a 401 response MUST send at least one `WWW-Authenticate` header field**. The client learns which scheme to use and can retry with fresh credentials.

HTTP Basic example:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo-api"
Cache-Control: no-store
```

Subsequent request:

```http
GET /api/profile HTTP/1.1
Host: app.example.test
Authorization: Basic <base64-of-username-colon-password>
```

The `Basic <...>` string is the wire credential, not the password hash format stored in a database. **Basic Base64 is not encryption**: HTTPS is mandatory and Authorization headers must never be logged. Wrong passwords or omitted Basic credentials → the application can return 401.

**Do not customize a 401 response via `response.setStatus(401)` while dropping `WWW-Authenticate`** and still call it standard HTTP authentication. When configuring Basic/Bearer, use the appropriate `AuthenticationEntryPoint` to generate the challenge. Some non-HTTP-challenge JSON systems return 401 under a different convention, yet you must understand the RFC boundary and client behavior.

### 2.2. 403 Forbidden

HTTP 403 states that the server understood the request but refuses to execute it. Even when credentials are valid, **permissions may still be insufficient**.

```http
GET /api/admin HTTP/1.1
Host: app.example.test
Authorization: Basic <valid-alice-credentials>
```

Alice is authenticated and has `ROLE_USER`, while the endpoint requires `ROLE_ADMIN`:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You are not permitted to access this resource."
}
```

The JSON above is an **application-formatted response example** (Problem Details under RFC 9457), **not a mandatory Spring Security default body**. Many setups return an empty body, an HTML error page, or a custom error structure. Status 403 does not mean "wrong password".

### 2.3. WWW-Authenticate and Scheme Differences

- **401** under RFC 9110 requires `WWW-Authenticate` and may specify `Basic`, `Bearer`, or another scheme; it does not always mean Basic.
- **403** is not required to carry `WWW-Authenticate` in every case. However, an **OAuth Bearer 403** with `insufficient_scope` **may carry** `WWW-Authenticate: Bearer ...` per RFC 6750.
- A **407 Proxy Authentication Required** response uses `Proxy-Authenticate`, not an origin server's 401/403. Distinguish gateways/proxies rejecting requests before reaching Spring.
- **404 Not Found** means the resource does not exist or may be used by policy to hide unauthorized resources; never treat 404 as universally meaning authorization success or failure.

## 3. Processing Flow in Spring Security Servlet

Spring Security separates errors requiring **authentication initiation** from **access denial** using key components:

- `SecurityContextHolder` / `Authentication`: current identity and list of authorities.
- `AuthorizationFilter` (with `authorizeHttpRequests`) or method security `@PreAuthorize`: enforces policy.
- `AuthenticationException`: an authentication step encountered an issue, such as invalid credentials.
- `AccessDeniedException`: an access rule denied the request.
- `ExceptionTranslationFilter`: translates security exceptions from downstream filters into the corresponding action.
- `AuthenticationEntryPoint`: **starts/requests authentication** (401 Basic/Bearer, or 302 Form Login).
- `AccessDeniedHandler`: handles **insufficient permissions** for an authenticated user, typically 403.

### 3.1. Decision Diagram

```text
HTTP request
    |
    v
SecurityFilterChain
    |
    | Authentication filters decode cookie/Basic/Bearer/session...
    | CsrfFilter/CorsFilter may block earlier in some scenarios
    v
AuthorizationFilter / @PreAuthorize
    |
    +---- Access GRANTED ------------------> Controller / resource
    |
    +---- Access DENIED: AccessDeniedException
                         |
                         v
                ExceptionTranslationFilter
                         |
                  Authentication trustworthy enough?
                  /                    \
             NO /                      \ YES
               v                        v
        AuthenticationEntryPoint     AccessDeniedHandler
        (401 or 302,               (usually HTTP 403)
         depending on auth scheme)

AuthenticationException from downstream:
    -> AuthenticationEntryPoint (401/302 depending on scheme)
```

Technical note: authentication filters such as `BasicAuthenticationFilter` or `BearerTokenAuthenticationFilter` can **directly invoke** `AuthenticationEntryPoint`/failure handlers when authentication fails; not every exception in the entire chain passes through `ExceptionTranslationFilter`. This filter is especially crucial when authorization or method security throws exceptions within the segment it wraps.

### 3.2. AccessDeniedException Does Not Always Turn into 403

If an **anonymous** user requests an ADMIN-only route, Spring Security normally receives an `AccessDeniedException` from the authorization rule. However, `ExceptionTranslationFilter` sees the user is not authenticated and delegates to `AuthenticationEntryPoint`:

- For Basic/Bearer APIs: typically **401 challenge**.
- For Form Login: typically **302 redirect to /login**.

If a user is **sufficiently authenticated** yet lacks a role/scope: it routes to `AccessDeniedHandler`, typically **403**. That is why **the exact same route** can return 401 when anonymous yet 403 when Alice is logged in and lacks permissions.

### 3.3. AnonymousAuthenticationToken Causes Confusion

Spring Security may place an `AnonymousAuthenticationToken` in SecurityContext rather than leaving `Authentication=null`. That token type can have `isAuthenticated()=true` on the object's API yet **is not treated as a real logged-in user** by the authorization DSL `authenticated()`. Spring uses its anonymous/trust resolver mechanism to enforce rules properly.

**Do not write your own check like:**

```java
Authentication auth = SecurityContextHolder
        .getContext().getAuthentication();
if (auth != null && auth.isAuthenticated()) {
    // Wrong if treating this as sufficient proof that a real user is logged in.
}
```

Use Spring Security's `.authenticated()`, `.hasRole(...)`, `@PreAuthorize`, or `AuthenticationTrustResolver` when checking for anonymous programmatically. Do not rewrite filters relying only on the `isAuthenticated()` boolean.

**Remember-me/partial authentication** may also require stronger authentication on endpoints demanding full authentication, depending on rules; do not classify every `Authentication != null` object as "fully authorized".

## 4. One Route, Multiple Statuses: Typical Cases

Suppose GET `/api/admin` requires `ROLE_ADMIN`.

| Caller | Credential | Authentication Result | Authorization | Response in Example Basic API |
| --- | --- | --- | --- | --- |
| Anonymous browser | None | No logged-in user | Lacking role | **401** + Basic challenge |
| Alice | **Wrong** Basic username/password | Authentication failed | Role not evaluated as authenticated | **401** + Basic challenge |
| Alice | Valid Basic, `ROLE_USER` | Authentication succeeded | Missing `ROLE_ADMIN` | **403** |
| Admin | Valid Basic, `ROLE_ADMIN` | Authentication succeeded | Sufficient role | **200** |
| Alice | Valid Basic yet bad CSRF on **POST** | May be blocked at CSRF filter before authorization | CSRF failed | **403**, does not prove missing role |
| Alice | Valid Basic, `ROLE_ADMIN` yet different tenant | Authenticated | Business authorization deny | **403** or hide resource with 404 if policy allows |

These responses assume the Basic API project in section 7. In Form Login, anonymous hits to protected pages may receive **302**; in Resource Server, invalid Bearer tokens have their own challenges; with custom handlers/WAFs, outcomes may differ. Thus **the status code derives from authentication type + exception timing + config**, not solely from roles.

## 5. Browser Form Login: 302 Does Not Mean 401 or Authenticated

Spring MVC applications using `formLogin()` typically interact via browser:

```text
Anonymous GET /admin
    |
    -> authorization deny
    -> LoginUrlAuthenticationEntryPoint
    -> HTTP 302 Location: /login
    |
    -> Browser GET /login
    -> HTTP 200 HTML login page
    |
    -> POST /login with username, password, CSRF
           -> Correct: redirect success target
           -> Wrong: redirect /login?error
    |
    -> Logged-in USER GET /admin
           -> HTTP 403 (lacking ROLE_ADMIN)
```

**Testing tip:** do not see `GET /login` returning 200 and conclude "user accessed /admin". An HTTP client that auto-follows redirects can hide the initial 302 status and show only the 200 of **the login page**. Disable auto-follow redirects or inspect `Location` and the **final URL**.

HTTP example:

```http
HTTP/1.1 302 Found
Location: http://localhost:8080/login
```

Because an HTML browser needs a page to enter credentials, redirecting is natural behavior; **not returning 401 on an unauthenticated route is not a security flaw**.

For JSON-returning APIs, HTML login redirects usually create poor UX: frontends get HTML instead of JSON, and `fetch` may follow the redirect and fail parsing. Design **separate `SecurityFilterChain`s or EntryPoints** for Basic/Bearer APIs and web form login if one app serves both.

## 6. Bearer Access Tokens: RFC 6750, 401 invalid_token, 403 insufficient_scope

In API applications authenticating via OAuth2 Bearer tokens, RFC 6750 adds specific response rules. Spring Security Resource Server provides `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler` for this.

### 6.1. Missing Token

```http
GET /reports HTTP/1.1
Host: api.example.test
```

Example response per RFC 6750:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api"
```

When there is **no token**, do not emit unnecessary `error_description`/details. The API is asking the client to supply an appropriate Bearer token.

### 6.2. Token Present but Invalid

Errors such as bad signature, expired `exp`, premature `nbf`, untrusted issuer, wrong audience for the API, or revoked token per validator can fail authentication:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api", error="invalid_token"
```

This is an illustrative status/challenge. Exact header attributes are determined by provider/version/config; do not assume Spring always sends `realm` or `error_description` matching sample strings verbatim.

### 6.3. Valid Token but Lacking Scope

Token is valid for issuer, signature, audience, and lifetime, yet carries `scope="profile"` while `GET /reports` requires `reports.read`:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="reports-api",
                  error="insufficient_scope",
                  scope="reports.read"
```

Under RFC 6750, `insufficient_scope` **SHOULD** return 403; the `scope` attribute is optional. Spring's `BearerTokenAccessDeniedHandler` can report `insufficient_scope` only when it recognizes a valid OAuth2 Authentication is already present; otherwise it may emit just the scheme/realm. **Do not write tests requiring the exact `scope=...` string unless your application configures that information.**

### 6.4. Malformed Tokens Are Sometimes Not 401

Under RFC 6750, `invalid_request` from sending tokens via multiple methods, malformed request syntax, or invalid parameters can return **400 Bad Request**. Do not lump **every** Bearer token error into 401 or 403.

### 6.5. API Authorization Still Stays Separate from Authentication

After the Resource Server verifies a token, Spring can map scope `reports.read` to authority `SCOPE_reports.read`. The rule:

```java
.requestMatchers("/reports/**")
.hasAuthority("SCOPE_reports.read")
```

decides access permissions only; it **does not** validate JWT signatures or issuer/audience if `JwtDecoder` is misconfigured. And a validly signed JWT issued for a different client/API still must not be accepted.

### 6.6. Illustrative Resource Server Config, Separate from the Basic Example

In another Spring Boot 3.x project with `spring-boot-starter-oauth2-resource-server` and a real OAuth/OIDC provider:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/tenant
          audiences: api://reports
```

Runs only when a real issuer serves metadata/JWKS and tokens are issued for the right audience. `issuer.example.test` is an illustrative hostname.

SecurityFilterChain (placed in the **Resource Server app**, not alongside section 7's Basic chain without designing matchers/order):

```java
@Bean
SecurityFilterChain reportApi(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/reports/**")
                .hasAuthority("SCOPE_reports.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}
```

The above is a **fragment inside a `@Configuration` class**, requiring imports for `HttpSecurity`, `SecurityFilterChain`, `Customizer`, and a Boot-configured JWT decoder bean. `oauth2ResourceServer().jwt()` **does not automatically enforce the right audience unless you configure validation**. You must verify issuer, audience, expiry, scope, and business authorization.

## 7. Java 17 + Spring Boot 3 / Spring Security 6 Example: HTTP Basic 401/403

The hands-on example below intentionally uses **HTTP Basic** to show 401/403 clearly without needing an OAuth server, JWTs, or a browser login form. It is a minimal **Servlet MVC** project using **Spring Security 6.x**. Localhost addresses are for development only; HTTPS is mandatory in real systems.

### 7.1. Project Setup and Dependencies

Create a Spring Boot 3.x project with Java 17+ from Spring Initializr, selecting Gradle Groovy, Spring Web, and Spring Security. Add test support in `build.gradle` with the Boot plugin already applied:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 7.2. Main Application

File `src/main/java/com/example/authstatus/AuthStatusApplication.java`:

```java
package com.example.authstatus;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthStatusApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthStatusApplication.class, args);
    }
}
```

### 7.3. SecurityFilterChain

File `src/main/java/com/example/authstatus/SecurityConfig.java`:

```java
package com.example.authstatus;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/profile", "/api/settings")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}
```

**Explanation:**

- `/api/public` permits anonymous access; requests sending no credentials return 200.
- `/api/profile` requires authentication; anonymous or bad Basic credentials return 401 with a Basic challenge in the standard flow.
- `/api/admin` requires `ROLE_ADMIN`; authenticated Alice with `ROLE_USER` receives 403, while admin is permitted.
- `/api/settings` requires authentication, yet **CSRF remains enabled by default**, intentionally showing that a POST with valid Basic credentials can still get 403 due to a missing CSRF token.
- `formLogin()` is not enabled in this example, avoiding confusion with 302 redirects when testing Basic.
- `.anyRequest().denyAll()` denies all other URLs; for anonymous denied routes, EntryPoint can return 401. Do not mistake this for application 404 behavior.

With browser clients, HTTP Basic can be cached by the browser and **automatically attach Authorization** on subsequent requests. Therefore never disable CSRF by default merely because an app uses Basic; CSRF depends on the browser's ability to auto-attach credentials. Bearer APIs accepting tokens passed explicitly in JS headers follow a different model, though how clients store/send tokens must still be analyzed.

### 7.4. Controller

File `src/main/java/com/example/authstatus/ApiController.java`:

```java
package com.example.authstatus;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public String publicMessage() {
        return "public";
    }

    @GetMapping("/api/profile")
    public String profile(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }

    @PostMapping("/api/settings")
    public String settings() {
        return "updated";
    }
}
```

When roles suffice, GET returns the corresponding body. `POST /api/settings` exists to test CSRF, not as a real settings persistence app.

### 7.5. Testing with curl

Start the created project:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

A few illustrative commands; run in a development terminal, **never send real Basic passwords to services without TLS**, and note that command-line arguments can appear in process history:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/profile
curl -i -u alice:alice-pass http://localhost:8080/api/profile
curl -i -u alice:alice-pass http://localhost:8080/api/admin
curl -i -u admin:admin-pass http://localhost:8080/api/admin
curl -i -u alice:wrong http://localhost:8080/api/profile
```

Expected statuses:

| Request | Status | Basis |
| --- | --- | --- |
| `GET /api/public` anonymous | **200** | permitAll |
| `GET /api/profile` anonymous | **401** | Missing HTTP Basic authentication; includes challenge |
| `GET /api/profile` with valid Alice | **200** | authenticated |
| `GET /api/admin` with valid Alice | **403** | ROLE_USER ≠ ROLE_ADMIN |
| `GET /api/admin` with valid Admin | **200** | ROLE_ADMIN |
| `GET /api/profile` with Alice wrong password | **401** | Authentication failed |

This is the **expected behavior of this exact demo config**. Real-world tests should inspect both status and `WWW-Authenticate` to ensure reverse proxies or other interceptors did not alter responses.

### 7.6. CSRF 403 Even with Valid Credentials

```http
POST /api/settings HTTP/1.1
Host: localhost:8080
Authorization: Basic <valid-alice-credential>
Content-Type: application/x-www-form-urlencoded

theme=dark
```

If the request lacks a valid CSRF token, Spring Security returns **403** by default. The reason is not that Alice lacks permission for `/api/settings`; the request was blocked by **CSRF protection**. For a POST to succeed in MVC tests, send an app-issued CSRF token matching the session/repository, or design an API that does not rely on browser auto-attached credentials and set an appropriate CSRF policy.

Sending a fake header like `X-CSRF-TOKEN: anything` unrelated to the token repository/session should still be rejected by Spring Security. Do not disable CSRF across the whole web app just to get a 200 POST example.

## 8. MockMvc Integration Tests: Asserting 401, 403, and Success Paths

Create `src/test/java/com/example/authstatus/ResponseStatusTest.java` inside section 7's Boot project:

```java
package com.example.authstatus;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ResponseStatusTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicResourceAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void missingCredentialsUsesBasicChallenge() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                    HttpHeaders.WWW_AUTHENTICATE, containsString("Basic")));
    }

    @Test
    void wrongPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedAdminGets200() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void validPasswordDoesNotBypassCsrf() throws Exception {
        mvc.perform(post("/api/settings")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validPasswordAndCsrfCanPost() throws Exception {
        mvc.perform(post("/api/settings")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf()))
            .andExpect(status().isOk());
    }
}
```

This is a **test class running inside Spring Boot 3.x** with the two declared test dependencies, not a program run directly via `javac`. Tests use `httpBasic(...)` to exercise **the real Basic authentication path through SecurityFilterChain**, without mocking roles. Spring Security Test's `csrf()` generates a matching CSRF token for MockMvc.

**Common pitfall:** `.with(user("alice").roles("ADMIN"))` or `@WithMockUser(roles="ADMIN")` tests only **authorization** given a mocked principal, **not actual Basic password authentication**. Keep both kinds of tests with clearly stated goals.

Since the demo uses BCrypt password encoding, each startup generates a new hash while the fixture's raw passwords remain `alice-pass` and `admin-pass`. Expected statuses remain consistent if SecurityFilterChain loads properly without extra filters.

### Checking More Than Just HTTP Status

A 403 test for missing roles should also verify the controller produced no side effects. For a database, verify no record was created; for payments, verify no event was emitted. A 302/403 response alone does not rule out a controller having executed before denial if you placed security at the wrong layer.

## 9. Why Is 403 Not Enough to Conclude "Already Authenticated"?

There are at least six sources of 403 besides lacking a role:

1. **CSRF:** POST/PUT/PATCH/DELETE via cookies or browser Basic missing a valid CSRF token. `CsrfFilter` can reject before the normal EntryPoint/authorization branch.
2. **CORS:** Cross-origin request outside the allowlist; browsers report CORS errors and servers/proxies reject preflight or responses; this says nothing about whether the user is Alice or Bob.
3. **WAF/reverse proxy/API Gateway:** Nginx, CDN, rate-limiting policies, or edge ACLs can return 403 before requests reach the JVM. Spring logs may never see the request.
4. **Custom AuthenticationEntryPoint:** If no scheme is configured to emit 401/302, an EntryPoint like `Http403ForbiddenEntryPoint` can return 403 to **anonymous** callers. That cannot be inferred as an authenticated user.
5. **Method/business authorization:** `@PreAuthorize`, ownership, tenant guards, feature policies, or controllers returning 403 directly may not follow the filter-chain branch you assume.
6. **Path/method policy:** Matchers or `denyAll()` hitting an unintended endpoint, URLs with different context paths, wrong filter-chain ordering, or method-blocking policies. Depending on authentication and EntryPoint, this can yield 401 or 403.

Thus the right formula is:

- **Identify endpoint, HTTP method, security chain, and credential type.**
- **Verify whether authentication succeeded**, inspecting principal and authorities safely.
- **Identify which filter/handler emitted the response**, inspecting `WWW-Authenticate`/`Location`.
- **Only then** conclude whether authentication or permission is missing.

Do not fix 403 errors by automatically forcing user logout in every case; if 403 stems from CSRF or missing roles, re-logging in may not resolve it and causes loops.

## 10. ExceptionHandlingConfigurer: Picking the Right EntryPoint and DeniedHandler

In Servlet Security, the DSL typically looks like:

```java
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint(myAuthenticationEntryPoint)
    .accessDeniedHandler(myAccessDeniedHandler));
```

This is an **illustrative API**: `myAuthenticationEntryPoint`/`myAccessDeniedHandler` must be beans/instances you created. Do not drop those two undefined variable names into section 7's demo class and try to run it. The hooks serve distinct purposes:

- `AuthenticationEntryPoint` handles requests needing authentication started: Basic/Bearer 401 with challenge, LoginUrl 302, or an appropriate UI mechanism.
- `AccessDeniedHandler` handles denied permissions when the subject is already authenticated in the right branch: typically 403.
- `ExceptionTranslationFilter` **translates exceptions into those two choices**; it does not replace `AuthorizationManager` in deciding permissions.

### 10.1. Customizing the 403 Body While Keeping the 401 HTTP Basic Challenge

In the existing Basic project, if you want a JSON response for 403, you can configure **only** `AccessDeniedHandler`, leaving `httpBasic()` to emit the standard 401 challenge:

```java
// Additional configuration snippet inside existing SecurityFilterChain.
http.exceptionHandling(ex -> ex
    .accessDeniedHandler((request, response, error) -> {
        response.setStatus(403);
        response.setContentType("application/problem+json");
        response.setCharacterEncoding("UTF-8");
        response.getWriter().write(
            "{\"type\":\"about:blank\",\"title\":\"Forbidden\"," +
            "\"status\":403}");
    }));
```

If you customize the 401 AuthenticationEntryPoint, **preserve the appropriate `WWW-Authenticate`** for Basic/Bearer. Never use one shared handler forcing status 403 for both `AuthenticationException` and `AccessDeniedException` just so the frontend "looks uniform".

Separate error formatting from security policy. When Problem Details needs `type`/`title`/`status`/correlation ID, never leak stack traces, user existence, password correctness details, token signature contents, sensitive internal role names, or object owner IDs.

### 10.2. When One Application Serves Both Web Forms and REST APIs

You can define **two `SecurityFilterChain`s by matcher/priority**:

- `/api/**`: authenticated by Bearer or Basic; unauthorized returns 401 challenge; denied returns 403 JSON.
- `/web/**`: formLogin; anonymous redirects 302 to login page; authenticated lacking permission returns 403 HTML/Access Denied page.

Use `@Order(1)` with `securityMatcher("/api/**")` and `@Order(2)` or a fallback chain for web; **never let APIs fall into the formLogin chain**, which causes `fetch` clients to receive HTML login pages. Prefer protocol-specific configuration and inspect `FilterChainProxy` traces to confirm which chain matched. This is an architectural guideline—do not copy two chains with the same matcher without defining priority and entry points.

**Protect CSRF per chain:** cookie-based web forms require CSRF; pure Bearer-header APIs not auto-attached by browsers may use another policy. Do not disable CSRF app-wide simply because one slice uses JWT.

## 11. How Should Frontends and HTTP Clients Handle 401/403?

### 11.1. Handling 401

- If a Bearer API returns 401 `invalid_token`: try refreshing the access token per standard OAuth client rules (if refresh token/rotation is valid), then retry at most once for eligible requests; never retry infinitely.
- If no session/refresh is available: route to the login UI or notify that re-login is needed.
- With HTTP Basic: the app or browser may prompt for credentials; never log Authorization headers or passwords.
- When the server returns 401 due to a revoked token or wrong issuer: do not assume refreshing will always fix it; investigate security incidents/config.
- Do not redirect-to-login on the frontend for **every** 403 response; an already logged-in user might simply lack permission.

### 11.2. Handling 403

- Display a neutral "You do not have permission to perform this action" without exposing role/tenant/owner metadata.
- With Bearer `insufficient_scope`, if the app has an additional-consent flow, guide the user to re-consent/re-authorize; do not spam the same token.
- With CSRF 403, re-sync the session/CSRF token securely, fix the form/header, and retry with duplicate-action protection; **never disable CSRF**.
- With WAF/CORS/edge 403, inspect the logs/headers/correlation ID of the layer emitting the error before changing Spring policies.
- Do not automatically wipe local sessions and force re-login solely for a missing role; avoid pointless logouts.

### 11.3. Avoid Auto-Following Redirects Misclassifying Statuses

HTTP libraries, browsers, and `fetch` can **follow 302 redirects**. If an API's initial response is 302 to `/login`, the client may receive a 200 HTML login page and fail JSON parsing. Debug via DevTools → Network across the redirect chain, or disable redirect following in HTTP client tests. When configuring APIs, ensure the EntryPoint emits a 401 challenge rather than an HTML redirect.

### 11.4. Expose Minimal Information in Responses

Never expose differences enabling account enumeration ("user admin exists but password is wrong", "user bob does not exist"), and never put JWTs, CSRF tokens, or stack traces in error bodies. Internal logs can classify `authentication_failure`, `access_denied`, and `csrf_rejected` by correlation ID; caller responses should hold only what is needed to take valid action.

## 12. Easily Confused Tests and How to Write Them Correctly

| Test ID | Request | Precondition | Expected Outcome in Demo Config |
| --- | --- | --- | --- |
| A01 | GET `/api/public` | No credentials | 200 |
| A02 | GET `/api/profile` | No credentials | 401 + Basic challenge |
| A03 | GET `/api/profile` | Basic Alice wrong password | 401 |
| A04 | GET `/api/profile` | Basic Alice valid | 200 |
| A05 | GET `/api/admin` | No credentials | 401 + Basic challenge |
| A06 | GET `/api/admin` | Basic Alice valid, `ROLE_USER` | 403 |
| A07 | GET `/api/admin` | Basic Admin valid, `ROLE_ADMIN` | 200 |
| A08 | POST `/api/settings` | Basic Alice valid, **CSRF missing** | 403 due to CSRF |
| A09 | POST `/api/settings` | Basic Alice valid, CSRF valid | 200 |
| A10 | POST `/api/settings` | Anonymous, CSRF missing | Usually 403 CSRF; do not infer anonymous is authenticated |
| F01 | GET `/web/admin` | Form Login anonymous | Usually 302 to login |
| F02 | GET `/web/admin` | Session user logged in, lacking ROLE_ADMIN | 403 |
| F03 | POST `/login` | Wrong password + valid CSRF | Usually 302 to `/login?error` |
| B01 | GET `/reports` | Bearer token missing | 401 Bearer challenge |
| B02 | GET `/reports` | Bearer token past `exp` | 401 `invalid_token` |
| B03 | GET `/reports` | Valid Bearer token, lacking scope | 403 `insufficient_scope` if valid OAuth authentication and handler supports it |
| B04 | GET `/reports` | Bearer token right scope yet wrong aud | 401 because token is invalid for the API |
| B05 | GET `/reports` | Malformed Bearer token request | Possibly 400 `invalid_request` |
| G01 | GET resource | WAF blocks before JVM | 403 from edge, no Spring trace |
| G02 | OPTIONS preflight | CORS disallows origin | Browser may report CORS; exact response depends on layer |
| M01 | POST domain action | Principal has role yet does not own resource | 403 or 404 per policy, no side effects |
| M02 | POST domain action | Valid authentication yet bad CSRF | 403; do not ask to re-login instead |

**Some tests cover scenarios outside the Basic project**, requiring Form Login, Resource Server, or WAF/CORS setups accordingly. Do not expect all 22 tests to pass against section 7's single SecurityFilterChain.

When testing 403 for missing permissions, ensure **valid credentials and valid CSRF**. If CSRF blocks first, the test can pass with 403 **even if the role rule is broken**, creating a false positive. Use GET when you want to measure authorization without state-changing CSRF noise.

## 13. Standalone Java 17: A 401/403 Status Model for Self-Testing

The following example uses neither Spring, Servlets, nor JWTs. It is a **small decision model** highlighting the difference between *unauthenticated*, *insufficient permission*, and *early CSRF block*, without claiming to replicate the full ExceptionTranslationFilter. Save as `AuthenticationStatusLab.java`.

```java
public final class AuthenticationStatusLab {

    enum Identity {
        ANONYMOUS,
        USER,
        ADMIN
    }

    record Request(
            Identity identity,
            boolean requiresAdmin,
            boolean csrfRequired,
            boolean csrfValid) {}

    static int status(Request request) {
        // In this model, the CSRF filter can block earlier.
        if (request.csrfRequired() && !request.csrfValid()) {
            return 403;
        }
        if (request.identity() == Identity.ANONYMOUS) {
            return 401;
        }
        if (request.requiresAdmin()
                && request.identity() != Identity.ADMIN) {
            return 403;
        }
        return 200;
    }

    public static void main(String[] args) {
        System.out.println("anonymousProfile=" +
                status(new Request(Identity.ANONYMOUS,
                        false, false, true)));

        System.out.println("aliceProfile=" +
                status(new Request(Identity.USER,
                        false, false, true)));

        System.out.println("aliceAdmin=" +
                status(new Request(Identity.USER,
                        true, false, true)));

        System.out.println("adminAdmin=" +
                status(new Request(Identity.ADMIN,
                        true, false, true)));

        System.out.println("csrfBeforeAuth=" +
                status(new Request(Identity.ANONYMOUS,
                        false, true, false)));

        System.out.println("csrfAfterAuth=" +
                status(new Request(Identity.ADMIN,
                        true, true, false)));
    }
}
```

Run with JDK 17 or newer:

```bash
javac AuthenticationStatusLab.java
java AuthenticationStatusLab
```

Exact stdout:

```text
anonymousProfile=401
aliceProfile=200
aliceAdmin=403
adminAdmin=200
csrfBeforeAuth=403
csrfAfterAuth=403
```

Meaning:

- `anonymousProfile=401`: no authentication yet on a protected route, so REST challenge logic asks to log in.
- `aliceProfile=200`: credentials assumed valid and route requires only authenticated.
- `aliceAdmin=403`: Alice is authenticated yet lacks the role.
- `adminAdmin=200`: has both authentication and permission.
- `csrfBeforeAuth=403` **key point**: even an anonymous request can receive 403 because the CSRF filter blocks **before** permission checks.
- `csrfAfterAuth=403`: even Admin cannot bypass CSRF when the request requires CSRF.

**Limitations:** the program does not implement `WWW-Authenticate`, Basic password validation, Sessions, OAuth2 Bearer decoders, 302 Form Login, or actual Spring CSRF filters. It models the decision boundary, while section 8's MockMvc tests verify the real filter chain.

## 14. Diagnostic Troubleshooting Order Instead of Guessing from Status

When users report "already logged in yet still getting 403", work from **outside in**:

1. **Record request method + path + scheme + correlation ID** (never log credentials). Is it GET/POST, what is the actual path, context path, domain, and API/Web?
2. **Identify the original response**: status 401/403/302? Any `WWW-Authenticate: Basic/Bearer`? Any `Location: /login`? Signs of CDN/WAF/gateway?
3. **Identify the matching security chain**: did `/api/**` accidentally enter the form-login chain? Are `@Order` and `securityMatcher` sensible?
4. **Verify whether authentication succeeded**: are Basic username/password, JWT signature/issuer/audience/expiry, session cookie, and principal valid? AnonymousAuthenticationToken is not a logged-in user.
5. **If auth is present**, read the authorities issued by the trusted authentication source: `ROLE_USER` or `ROLE_ADMIN`, `SCOPE_x` or `scope`? Remember `hasRole("ADMIN")` requires `ROLE_ADMIN` by default, while `hasAuthority("SCOPE_reports.read")` matches the exact name.
6. **CSRF/CORS before authorization**: on POST 403, check CSRF token/cookie and Origin/Fetch metadata/Referer policy per app. Never strip CSRF carelessly.
7. **Method security and business logic**: `@PreAuthorize`, owner/tenant, locked account, MFA step-up, and other deny rules?
8. **Which handler sent the response?** `AuthenticationEntryPoint`, `AccessDeniedHandler`, `CsrfFilter`, controller, gateway, or exception mapper? Never change statuses blindly before locating the source.
9. **Verify no side effects occurred**: rejected requests must not mutate the database or emit domain events.
10. **Cross-check against the API design**: REST needs proper 401/403, browsers need login redirects, Bearer needs RFC 6750 challenges, and UIs need safe messages.

### Common Symptoms

| Observation | Possible Cause | Fix |
| --- | --- | --- |
| Anonymous GET API returns 302 then HTML | API hits FormLogin EntryPoint | Separate API chain, use proper Basic/Bearer EntryPoint |
| Anonymous GET API returns 403 when expecting 401 | No proper EntryPoint / using Http403ForbiddenEntryPoint | Configure scheme/API challenge and verify filter chain |
| User gets 403 despite having `ROLE_ADMIN` in DB | Spring Authentication lacks authority, or wrong prefix/mapping | Check `GrantedAuthority` from trusted source and role mapping |
| Valid JWT yet 401 | Wrong issuer/audience/expiry/signature, wrong JWKS | Read secret-filtered auth failure; fix validation rather than bypassing |
| Valid JWT yet 403 | Missing scope/role/ownership, Bearer access denied | Request right scope, fix business policy mapping |
| POST 403 while GET 200 | Missing CSRF token or method-specific policy | Check CSRF and request matchers; never disable globally |
| Basic/Bearer header vanishes | Proxy/gateway fails to forward Authorization | Configure proxy safely, never expose tokens in logs |
| Passes with `@WithMockUser`, fails real login | Test bypasses AuthenticationProvider | Test real Basic/Bearer/cookies with MockMvc integration |
| Browser fetch fails JSON parse with status 200 | Auto-followed 302 to `/login` returning HTML | Inspect redirect chain and Content-Type |
| Backend never sees 403 request | Edge/WAF/CORS blocks before Spring | Compare correlation IDs and gateway logs |
| User has role yet tenant object is denied | Ownership/tenant guard blocking properly | Do not bypass by recklessly granting ROLE_ADMIN |
| Custom EntryPoint returns 401 JSON without header | Missing `WWW-Authenticate` per HTTP challenge spec | Use Basic/Bearer EntryPoint or preserve challenge |
| Endless 401 loop after token refresh | Client interceptor retry loop, refresh failing | Bounded retries, invalidate credentials properly |
| Role treated as username | Mixing up Authentication and Authorization | Use principal for identity, authorities for permissions |

## 15. Checklist When Reviewing Spring Security Authentication Responses

- [ ] Distinguished **authentication** (missing/bad credentials) from **authorization** (authenticated yet lacking permissions).
- [ ] API 401 includes appropriate Basic/Bearer `WWW-Authenticate` per RFC 9110; not using one 403 handler for everything.
- [ ] 403 for an authenticated user lacking a role/scope is expected; do not force infinite re-logins.
- [ ] **403 does not prove authenticated**: checked CSRF, WAF, CORS, Http403ForbiddenEntryPoint, custom controllers, and route policies.
- [ ] Anonymous Form Login can receive **302** to login; tests do not confuse login page 200 with successful resource access.
- [ ] Spring `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, and `AccessDeniedHandler` are properly understood; authenticated vs anonymous is checked via Spring policy, not just `auth != null`.
- [ ] Basic/Bearer credentials are actually tested; `@WithMockUser` tests are not treated as proof of credential validation.
- [ ] Tested anonymous, wrong password, authenticated user lacking role, admin with role, invalid/insufficient-scope Bearer, POST missing CSRF, and happy path.
- [ ] On CSRF 403, the request is blocked before side effects; role-only tests supply valid CSRF to avoid false positives.
- [ ] UI handles 401 by requesting authentication, 403 with a permission/scope message, and does not wipe sessions needlessly.
- [ ] Verified issuer/audience/expiry for JWTs, `ROLE_` role prefix, `SCOPE_` scope prefix, and separate tenant/owner policies.
- [ ] Logs aid diagnostics without leaking Authorization headers, access tokens, passwords, cookies, or internal user details.

**Final summary:** **401** usually means *no valid authentication yet*, while **403** usually means *not permitted to perform what was requested*. Yet status is **the outcome of the entire flow and configuration**: in Spring Security, anonymous encountering `AccessDeniedException` can be routed to an EntryPoint yielding **401 or 302**, a logged-in user lacking permissions goes through AccessDeniedHandler yielding **403**, and CSRF/gateways can still produce **403 even when anonymous**. To conclude accurately, inspect auth scheme, filters/handlers, credentials, permissions, and HTTP method together.

### Standard References

- [RFC 9110 — HTTP Semantics, 401, 403 and WWW-Authenticate](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 6750 — Bearer Token Usage, invalid_token and insufficient_scope](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [Spring Security 6.5 — ExceptionTranslationFilter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html)
- [Spring Security 6.5 — Servlet Architecture and Handling Security Exceptions](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security — Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html)
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Bearer Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — MockMvc Authentication Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
