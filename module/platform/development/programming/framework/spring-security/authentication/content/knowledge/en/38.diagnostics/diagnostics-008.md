# CSRF Rejected Before Credentials Reach the Provider

## 1. Phenomenon and Conclusion to Verify

A user enters the right username/password into the login form yet receives **HTTP 403 Forbidden** when submitting `POST /login`. During debugging, breakpoints in `UserDetailsService.loadUserByUsername`, `PasswordEncoder.matches`, or `AuthenticationProvider.authenticate` never fire. Changing the right password to a wrong password produces the exact same result.

If the request is rejected by **`CsrfFilter`**, that is expected Spring Security behavior: the request **stops before `UsernamePasswordAuthenticationFilter`**, so `UsernamePasswordAuthenticationToken` is never created or passed to `AuthenticationManager` and the provider.

However, **not every HTTP 403 is a CSRF error**. An authorization rule, custom filter, access-denied handler, or gateway can also return 403. This lesson shows how to prove the exact cause using filter ordering, request/session traces, and a controlled test with a provider call counter.

### Objectives

1. Explain why CSRF protects **login POSTs** as well.
2. Understand the order `CsrfFilter → UsernamePasswordAuthenticationFilter → AuthenticationManager/Provider`.
3. Distinguish `MissingCsrfTokenException` and `InvalidCsrfTokenException`, and 403 from CSRF vs 401/302/403 from other layers.
4. Diagnose `_csrf` form parameters, session cookies, token repositories, request handlers, and masked-token semantics.
5. Handle HTML forms, Thymeleaf, SPAs, `fetch`, reverse proxies, and multiple `SecurityFilterChain`s.
6. Write JUnit 5/MockMvc tests in Spring Boot 3.x / Spring Security 6.x / Java 17+ proving **the provider is called 0 times** when CSRF fails.
7. Never disable CSRF globally as a workaround.
8. Provide a production investigation checklist that never exposes passwords, tokens, or session cookies.

**Core mindset:** CSRF is a **pre-authentication** protection step, not a password verification outcome.

## 2. Why Must `POST /login` Have a CSRF Token?

CSRF (Cross-Site Request Forgery) occurs when an attacker-controlled site tricks the user's browser into sending a request to a target site carrying credentials the browser attaches automatically, especially cookies.

A login request also **mutates session state**. Without CSRF protection, a malicious site could log the victim's browser into an attacker-controlled account (login CSRF), creating confusion between the account owner and the person using the browser and leading to unintended business consequences.

Protection model:

~~~text
Victim's browser
    |
    +--> unintended website attempts to send POST /login
                |
                v
          Spring Security
                |
                +--> CsrfFilter
                      |
                      +-- valid CSRF proof present? NO
                      |       → AccessDeniedHandler, usually 403
                      |
                      +-- YES
                              → credential-handling filter runs next
~~~

CSRF proof must come from a part of the request that an unintended site **cannot automatically supply validly just by letting the browser attach cookies**, such as a hidden form input or a header obtained from a trusted same-origin source.

- **A CSRF token is not an access token.**
- **A CSRF token does not verify passwords.**
- **A valid CSRF token does not mean the user is logged in.**
- **`permitAll("/login")` affects only authorization; it does not disable `CsrfFilter`.**

This is why a public endpoint for unauthenticated users can still require a CSRF token on POST.

## 3. Filter Order Determines Where the Request Stops

In Servlet Spring Security 6.x, `FilterChainProxy` selects a matching `SecurityFilterChain`. A typical order for form login is:

~~~text
POST /login
   |
   v
DelegatingFilterProxy
   |
   v
FilterChainProxy selects SecurityFilterChain
   |
   v
SecurityContextHolderFilter and infrastructure filters
   |
   v
CsrfFilter
   |
   +-- POST must undergo CSRF validation
   +-- load expected token from CsrfTokenRepository
   +-- resolve actual token via CsrfTokenRequestHandler
   +-- compare
       |
       +-- MISSING or INVALID
       |      → CsrfException
       |      → AccessDeniedHandler
       |      → typically HTTP 403
       |      → STOP, do not call chain.doFilter further
       |
       +-- VALID
              |
              v
       UsernamePasswordAuthenticationFilter
              |
              +-- read username/password from request
              +-- AuthenticationManager.authenticate(...)
              +-- AuthenticationProvider.authenticate(...)
              +-- UserDetailsService / PasswordEncoder
              +-- authentication success/failure handling
              |
              v
       remaining filters and authorization
~~~

Spring Security describes the conceptual order as **exploit protection before authentication, authentication before authorization**. `CsrfFilter` is an early checkpoint in the flow.

### Breakpoint Consequences

When CSRF is invalid:
- `AuthenticationProvider.authenticate()` **is never called**.
- `PasswordEncoder.matches()` **never runs**.
- The bad-credentials `AuthenticationFailureHandler` **does not necessarily run**, since the provider never threw `BadCredentialsException`.
- `AuthenticationSuccessHandler` does not run.
- No new authentication is created from that POST.

Therefore, if you only put logs inside the provider, you will see nothing and mistakenly conclude `AuthenticationManager` is misconfigured. First find **which filter terminated the request**.

**Limitation:** applications can have multiple chains, custom servlet filters, and varied authentication mechanisms. Do not guess the order if `/login` hits a different chain; inspect the actual chain at runtime.

## 4. Distinguishing Responses: 403, 302, 401, and 404

| Symptom | Common Source | Provider Called? | Investigation Direction |
|---|---|---|---|
| `POST /login` → 403, token missing | `CsrfFilter` | No | Form/cookie/CSRF |
| `POST /login` → 403, token wrong | `CsrfFilter` | No | Session/repository/handler |
| `POST /login` → 302 `/login?error` | Default authentication failure | Usually yes | Password, UDS, account flags |
| `POST /login` → 302 `/` or saved URL | Authentication success | Usually yes | Session and redirect |
| `GET /private` → 302 `/login` | Form login entry point | Not directly related | Unauthenticated |
| API `401` with `WWW-Authenticate` | Basic/Bearer entry point | Depends on mechanism | Credentials/token |
| `403` after authenticated request | Authorization/CSRF/custom rule | Situation-dependent | Exception/filter |
| `POST /login` → 404 | Wrong login processing path or chain | No | URL/matcher |
| Browser reports CORS failure | CORS/preflight/network | Request may not have reached provider | CORS/credentials |

These statuses/redirects are **common defaults**, not immutable rules. Custom `AccessDeniedHandler`, `AuthenticationEntryPoint`, `AuthenticationFailureHandler`, reverse proxies, or exception mappers can alter statuses/bodies.

**Diagnostic rule:** do not treat "response is 403" as enough to conclude CSRF; confirm via the exception/handler or a controlled test.

## 5. What Does `CsrfFilter` Check?

Spring Security Servlet enables CSRF by default for **unsafe HTTP methods** like `POST`, `PUT`, `PATCH`, `DELETE`. It normally skips `GET`, `HEAD`, `OPTIONS`, `TRACE` per the default matcher.

~~~text
GET /login
  → form page can generate/render the CSRF token
  → does not need to present CSRF proof like POST

POST /login
  → requires CSRF protection
  → actual token must match expected token
  → if wrong/missing, request is blocked before provider
~~~

Never turn state-changing actions into GET just to evade CSRF. Login submissions, logouts, password changes, contact verification, and write operations must use appropriate HTTP methods.

### 5.1. Expected Token vs Actual Token

- **Expected token** comes from `CsrfTokenRepository`. The default Servlet repository is usually `HttpSessionCsrfTokenRepository`, storing the token bound to `HttpSession`.
- **Actual token** comes from the HTTP request, usually form field `_csrf` or a CSRF header.
- **`CsrfTokenRequestHandler`** exposes the token as a request attribute and resolves the submitted token from headers/parameters.

If the request lacks a required expected token, you may see `MissingCsrfTokenException`. When an expected token exists yet the submitted token does not match, you may see `InvalidCsrfTokenException`. Both extend `CsrfException`, which extends `AccessDeniedException`.

**Do not conclude solely from the exception name that the browser omitted the token field**. The request may carry the right field name while the token belongs to another session or uses a different encoding than the handler expects.

### 5.2. The Session Is Part of Matching

~~~text
GET /login
    Cookie: JSESSIONID=A
    → hidden _csrf rendered for session A

POST /login
    Cookie: JSESSIONID=B or missing session A
    → expected token differs/missing
    → CSRF rejection before authentication
~~~

This happens when:
- the cookie was dropped by the browser due to `SameSite`, `Secure`, `Domain`, `Path`;
- the user left the login page open too long and the session expired;
- the cookie/session changed due to logout/login in another tab;
- a load balancer routed the POST to a node without shared sessions;
- old HTML forms were cached and reused across different sessions.

Record only session/cookie **presence/absence** when investigating; never put real `JSESSIONID` or `_csrf` values into logs.

## 6. HTML Forms and Thymeleaf: Where the CSRF Token Comes From

Standard form login typically sends:

~~~http
POST /login HTTP/1.1
Host: app.example.org
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=SESSION_VALUE

username=alice&password=...&_csrf=MASKED_TOKEN
~~~

The snippet above illustrates **field names only**, not real usable credentials or tokens.

Thymeleaf example:

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="utf-8"><title>Sign In</title></head>
<body>
  <form th:action="@{/login}" method="post">
    <label for="username">Username</label>
    <input id="username" name="username" autocomplete="username">

    <label for="password">Password</label>
    <input id="password" name="password" type="password"
           autocomplete="current-password">

    <button type="submit">Sign In</button>
  </form>
</body>
</html>
~~~

When the view engine integrates properly with `CsrfRequestDataValueProcessor`, Thymeleaf can **auto-generate the hidden CSRF input** for POST forms. If using another template engine without that integration, render the field explicitly on the server:

~~~html
<!-- Add manually only when the view layer does not auto-generate CSRF input -->
<input type="hidden" th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}">
~~~

The `th:` prefix is Thymeleaf syntax; use it inside an actual Thymeleaf template. **Do not insert two inputs both named `_csrf`** if the view layer already adds one automatically. Inspect the rendered DOM in the browser, not just template source.

### `permitAll` Does Not Bypass CSRF

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/login").permitAll()
        .anyRequest().authenticated())
    .formLogin(Customizer.withDefaults());
~~~

Anonymous requests are permitted to reach the login endpoint under authorization. `POST /login` still passes through `CsrfFilter`. Adding `permitAll` again will not fix a CSRF token mismatch.

## 7. Ordered Diagnostic Approach

### Step 1 — Verify the Real Request, Not Just UI Descriptions

In DevTools → Network, record:
- HTTP method, path, status, and redirect chain;
- whether `Content-Type` is `application/x-www-form-urlencoded`, `multipart/form-data`, or JSON;
- whether the token parameter or header is **present** (do not copy its value);
- whether the session cookie is sent (do not copy its value);
- whether the request crossed a redirect changing hostname/scheme/port;
- whether `/login` is indeed the URL handled by the login filter.

Never upload HAR files containing credentials/sessions/CSRF/bearer tokens to external tools.

### Step 2 — Identify the Matching `SecurityFilterChain`

Each `SecurityFilterChain` has its own matcher and order. If an `@Order(1)` chain handles `/api/**`, `POST /api/login` might **not** enter the chain containing `formLogin()`.

Enable DEBUG in test environments or briefly while investigating:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Inspect the `DefaultSecurityFilterChain` startup log: are `CsrfFilter`, `UsernamePasswordAuthenticationFilter`, and `AuthorizationFilter` present? If the chain lacks the login filter, do not debug another chain's provider.

TRACE gives extra detail yet must be reviewed for exposing headers/parameters and enabled only briefly under control.

### Step 3 — Confirm the Failure Originates in `CsrfFilter`

Strong signals:
1. `POST /login` with missing/wrong token returns 403.
2. `MissingCsrfTokenException` or `InvalidCsrfTokenException` appears in the security layer.
3. With the **same URL/method** and valid CSRF, the provider gets called.
4. A counter/breakpoint at the top of `AuthenticationProvider.authenticate` stays at **0** for CSRF-failing requests.

Do not rely on `AuthenticationFailureHandler` to catch these errors: that handler usually runs after the provider attempts authentication, whereas CSRF rejection happens beforehand.

### Step 4 — Find Why the Token Was Wrong

Check thoroughly:
- Did `GET /login` generate/render the token?
- Does the hidden form field or header use the right name?
- Do GET and POST share the same session/context?
- Does the frontend send cookies per policy?
- Was the token cleared after login/logout, or was an old form reused?
- Does `CsrfTokenRequestHandler` handle raw vs masked tokens properly?
- Is there a dedicated `CookieCsrfTokenRepository` for an SPA?
- Did a proxy/cache/CDN alter hostnames/cookies or cache login HTML?

### Step 5 — Once CSRF Passes, Inspect Credentials/Provider

After clearing `CsrfFilter`, verify:
- URL matches `loginProcessingUrl`.
- Form uses `username` and `password` or configured custom parameter names.
- `AuthenticationManager` and provider support `UsernamePasswordAuthenticationToken`.
- `UserDetailsService` loads the right account.
- `PasswordEncoder.matches` handles the stored hash format.
- Account is not locked/disabled/expired.
- Success/failure handlers redirect and persist sessions properly.

**Diagnosing in order prevents editing `PasswordEncoder` when the password never even reached it.**

## 8. Symptom → Cause → Remediation Matrix

| Symptom | Common Cause | Remediation |
|---|---|---|
| Form GET OK, login POST 403 | Form lacks `_csrf` | Render and submit token |
| Static HTML lacks hidden field | View has no CSRF integration | Generate input from server |
| Token present, POST still 403 | Session mismatch or handler reads wrongly | Check repository/handler/cookie |
| Logging in from stale tab after logout | Token cleared and form is stale | Reload form, fetch fresh token |
| SPA's first POST after login 403 | Old token cleared, deferred loading | Bootstrap fresh token |
| SPA reads raw cookie, server expects XOR masked | Incompatible request handler | Use official SPA configuration |
| Browser `fetch` lacks session cookie | `credentials`, `SameSite`, CORS, or cookie attributes | Fix cookie/credentials |
| Renamed CSRF header | Frontend and backend contracts differ | Align on `CsrfToken.getHeaderName()` |
| Form POSTs JSON to default `formLogin` | Default filter reads form parameters | Use form-urlencoded or dedicated JSON auth filter |
| `/api/login` 403 while `/login` OK | Different `SecurityFilterChain` | Check matcher/order |
| CSRF fails on one replica | Non-distributed session store | Use Spring Session / proper sticky routing |
| HTTP→HTTPS redirect drops cookie | Wrong Secure/domain/scheme | Fix public URL / trusted proxy |
| MockMvc POST 403 | Test omits `.with(csrf())` | Add CSRF proof on positive cases |
| `@WithMockUser` yet POST still 403 | Mock identity supplies no CSRF | Add `csrf()` separately |
| POST `/login` 302 error | Provider called, credentials wrong | Diagnose authentication |
| Protected GET 403 | Rule lacks authority or custom policy | Diagnose authorization |
| Browser reports CORS preflight error | `OPTIONS` blocked / CORS config | Diagnose CORS, do not assume CSRF |

A request can have multiple errors, yet **an earlier failure masks later ones**. Once CSRF is fixed, the app may start returning `/login?error` if the password was genuinely wrong.

## 9. Spring Security 6.x: Deferred Loading and XOR Tokens

Two key changes when upgrading Spring Security 5 → 6:

### 9.1. Deferred CSRF Loading

The CSRF token may be created/loaded only when actually needed, such as when:
- a POST requires validation;
- the server renders a form containing `_csrf`;
- an SPA explicitly bootstraps the token.

A GET page that does not use the CSRF token does not necessarily issue a new session/cookie. Therefore do not assume a token is always ready after any GET.

### 9.2. Masked vs Raw Token for BREACH Protection

`XorCsrfTokenRequestAttributeHandler` enables BREACH protection by default: the rendered hidden token can **differ as a string** across two renders while the repository still holds the same raw token.

~~~text
CsrfTokenRepository:
    rawToken = SECRET

HTML form render 1:
    _csrf = MASKED_VALUE_1

HTML form render 2:
    _csrf = MASKED_VALUE_2

POST:
    XorCsrfTokenRequestAttributeHandler
    → decodes masked value
    → compares against raw token in repository
~~~

Do not use `String.equals(maskedFormValue, rawRepositoryValue)` to diagnose errors. Resolution is performed by `CsrfTokenRequestHandler`.

### 9.3. `CookieCsrfTokenRepository` for SPAs

SPAs often use `CookieCsrfTokenRepository.withHttpOnlyFalse()` so JavaScript can read the CSRF cookie, usually named `XSRF-TOKEN`, and send the raw token in the `X-XSRF-TOKEN` header.

Switching the repository alone **is not enough** if the handler expects a masked value. Spring Security 6.5 documents `SpaCsrfTokenRequestHandler`:
- uses the plain handler when reading a raw token from headers;
- keeps the XOR handler when rendering tokens in HTML forms;
- proactively loads the deferred token so a fresh cookie is returned when needed.

Disabling `HttpOnly` applies only to the **CSRF cookie** when JS genuinely needs to read it. **Never** remove `HttpOnly` on authentication session cookies just to "debug easily".

## 10. After Login/Logout, Tokens Can Be Cleared

`CsrfAuthenticationStrategy` and `CsrfLogoutHandler` can clear the old token upon successful authentication or logout. An SPA holding token A from earlier may hit:

~~~text
GET CSRF bootstrap → SPA holds token A
POST /login with A → login succeeds
Authentication success → clears A
POST /settings with A → 403
~~~

**Solution:** the app must fetch a fresh token after login/logout and send it with the new session/cookie. With deferred loading, a GET that does not access/render the token may not issue a new one; provide an explicit bootstrap endpoint/handler.

Never resolve this with `permitAll("/settings")` or disabling CSRF on all POSTs.

## 11. Spring Boot 3.5 / Spring Security 6.5 / Java 17 Project

To prove **the provider is not called when CSRF fails**, we build a demo provider with a call counter. Form login uses Spring Security's real filter, not custom controller handling.

**Limitations:** this code is for learning/testing. The provider accepts only user `alice` with a test password from configuration; it does not replace production designs with persistent `UserDetailsService`, MFA/passkeys, rate limiting, or auditing.

### 11.1. Structure

~~~text
csrf-diagnosis/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/csrfdiagnosis/
    │   │   ├── CsrfDiagnosisApplication.java
    │   │   ├── RecordingAuthenticationProvider.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── PrivateController.java
    │   └── resources/application.yml
    └── test/java/com/example/csrfdiagnosis/
        └── CsrfBeforeProviderTest.java
~~~

### 11.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>csrf-diagnosis</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

The Spring Boot parent manages compatible dependency versions, including `spring-security-test` in test scope.

### 11.3. `application.yml`

~~~yaml
server:
  port: 8080

demo:
  user:
    password: ${DEMO_USER_PASSWORD}
~~~

When running locally, supply `DEMO_USER_PASSWORD`; in tests, `@SpringBootTest(properties=...)` supplies a dedicated test password so no environment variable is required.

### 11.4. `CsrfDiagnosisApplication.java`

~~~java
package com.example.csrfdiagnosis;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDiagnosisApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfDiagnosisApplication.class, args);
    }
}
~~~

### 11.5. `RecordingAuthenticationProvider.java`

~~~java
package com.example.csrfdiagnosis;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.core.env.Environment;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public final class RecordingAuthenticationProvider
        implements AuthenticationProvider {

    private final PasswordEncoder encoder;
    private final String storedHash;
    private final AtomicInteger calls = new AtomicInteger();

    public RecordingAuthenticationProvider(
            PasswordEncoder encoder, Environment environment) {
        this.encoder = encoder;
        String password =
                environment.getRequiredProperty("demo.user.password");
        this.storedHash = encoder.encode(password);
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {
        calls.incrementAndGet();

        String username = request.getName();
        String submitted = String.valueOf(
                request.getCredentials());

        if (!"alice".equals(username)
                || !encoder.matches(submitted, storedHash)) {
            throw new BadCredentialsException(
                    "Invalid credentials");
        }

        return UsernamePasswordAuthenticationToken.authenticated(
                "alice", null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Override
    public boolean supports(Class<?> type) {
        return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(type);
    }

    int calls() {
        return calls.get();
    }

    void resetCalls() {
        calls.set(0);
    }
}
~~~

The counter at the top of `authenticate()` proves it directly: when CSRF is invalid, it does not increment; when CSRF is valid, credential verification runs.

The password is encoded on bean creation; the test does not rely on plaintext strings in a DB. **Never use this single-user provider in production.**

### 11.6. `SecurityConfiguration.java`

~~~java
package com.example.csrfdiagnosis;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    AuthenticationManager authenticationManager(
            RecordingAuthenticationProvider provider) {
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, AuthenticationManager manager)
            throws Exception {

        return http
                .csrf(Customizer.withDefaults())
                .authenticationManager(manager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

`ProviderManager(List.of(provider))` guarantees this is the **sole provider of the demo `AuthenticationManager`**, making the counter unambiguous without guessing fallback providers. `formLogin` installs `UsernamePasswordAuthenticationFilter`. `csrf` stays at default. `permitAll` does not skip CSRF.

### 11.7. `PrivateController.java`

~~~java
package com.example.csrfdiagnosis;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PrivateController {
    @GetMapping("/private")
    public Map<String, Object> privateEndpoint(
            Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "authenticated", authentication.isAuthenticated());
    }
}
~~~

After a successful login, `GET /private` returns JSON equivalent to `{"username":"alice","authenticated":true}`. When anonymous, form login redirects to `/login`.

## 12. JUnit 5 / MockMvc: Proving CSRF Blocks Before the Provider

File `src/test/java/com/example/csrfdiagnosis/CsrfBeforeProviderTest.java`:

~~~java
package com.example.csrfdiagnosis;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(properties =
        "demo.user.password=local-only-test-password")
@AutoConfigureMockMvc
class CsrfBeforeProviderTest {

    @Autowired MockMvc mvc;
    @Autowired RecordingAuthenticationProvider provider;

    @BeforeEach
    void reset() {
        provider.resetCalls();
    }

    @Test
    void loginPageCanRenderTokenWithoutProvider()
            throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("_csrf")));
        assertEquals(0, provider.calls());
    }

    @Test
    void correctPasswordWithoutCsrfIsRejectedBeforeProvider()
            throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "local-only-test-password"))
            .andExpect(status().isForbidden())
            .andExpect(unauthenticated());
        assertEquals(0, provider.calls());
    }

    @Test
    void wrongPasswordWithoutCsrfIsAlsoRejectedBeforeProvider()
            throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "wrong"))
            .andExpect(status().isForbidden());
        assertEquals(0, provider.calls());
    }

    @Test
    void invalidCsrfIsRejectedBeforeProvider() throws Exception {
        mvc.perform(post("/login")
                .with(csrf().useInvalidToken())
                .param("username", "alice")
                .param("password", "local-only-test-password"))
            .andExpect(status().isForbidden());
        assertEquals(0, provider.calls());
    }

    @Test
    void correctPasswordWithCsrfReachesProvider()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "local-only-test-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("alice"));
        assertEquals(1, provider.calls());
    }

    @Test
    void wrongPasswordWithCsrfReachesProvider()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
        assertEquals(1, provider.calls());
    }

    @Test
    void formLoginHelperAlreadyIncludesValidCsrf()
            throws Exception {
        mvc.perform(formLogin()
                .user("alice")
                .password("local-only-test-password"))
            .andExpect(authenticated().withUsername("alice"));
        assertEquals(1, provider.calls());
    }
}
~~~

Run:

~~~bash
mvn clean test
~~~

**Expected:** 7 tests PASS, given Maven/JDK 17+ and matching dependencies. Reports are in `target/surefire-reports/`; exact Maven stdout varies across machines.

### 12.1. Test Result Matrix

| Request | Expected HTTP Status | Provider Calls |
|---|---|---:|
| `GET /login` | 200 | 0 |
| POST right password, **no CSRF** | **403** | **0** |
| POST wrong password, **no CSRF** | **403** | **0** |
| POST right password, **invalid CSRF** | **403** | **0** |
| POST right password, **valid CSRF** | 302 success | **1** |
| POST wrong password, **valid CSRF** | 302 `/login?error` | **1** |
| `formLogin()` helper, right password | 302 success | **1** |

Important note: `SecurityMockMvcRequestBuilders.formLogin()` **automatically attaches a valid CSRF token**. To test a missing token, use a raw `post("/login")` without `.with(csrf())`.

`@WithMockUser` does not supply a CSRF token for POST; `@AutoConfigureMockMvc(addFilters=false)` stops the test from verifying real filter behavior.

**Testing limitation:** MockMvc has a CSRF post-processor to test the filter chain, yet it does not prove a real browser kept cookies/sessions across a reverse proxy, multiple nodes, or SPA bootstrap. Additional integration/E2E tests are needed.

## 13. Standalone Java 17 Program: Order Before vs After Provider

Without Spring installed, the following program models the principle of **early return when CSRF fails**. It does not perform real cryptographic CSRF verification and **is not production authentication**.

File `CsrfBeforeProviderDemo.java`:

~~~java
public final class CsrfBeforeProviderDemo {

    enum CsrfResult {
        MISSING, INVALID, VALID
    }

    record LoginRequest(CsrfResult csrf, String password) {
    }

    static final class RecordingProvider {
        int calls;

        boolean authenticate(String password) {
            calls++;
            return "correct-test-password".equals(password);
        }
    }

    static String handle(
            LoginRequest request, RecordingProvider provider) {
        if (request.csrf() != CsrfResult.VALID) {
            return "403 CSRF";
        }
        return provider.authenticate(request.password())
                ? "302 HOME" : "302 LOGIN_ERROR";
    }

    static void show(
            String label, LoginRequest request,
            RecordingProvider provider) {
        System.out.println(label + "=" + handle(request, provider)
                + ", providerCalls=" + provider.calls);
    }

    public static void main(String[] args) {
        RecordingProvider provider = new RecordingProvider();
        show("missing", new LoginRequest(
                CsrfResult.MISSING, "correct-test-password"), provider);
        show("invalid", new LoginRequest(
                CsrfResult.INVALID, "correct-test-password"), provider);
        show("wrong", new LoginRequest(
                CsrfResult.VALID, "wrong"), provider);
        show("correct", new LoginRequest(
                CsrfResult.VALID, "correct-test-password"), provider);
    }
}
~~~

Run:

~~~bash
javac CsrfBeforeProviderDemo.java
java CsrfBeforeProviderDemo
~~~

**Exact stdout:**

~~~text
missing=403 CSRF, providerCalls=0
invalid=403 CSRF, providerCalls=0
wrong=302 LOGIN_ERROR, providerCalls=1
correct=302 HOME, providerCalls=2
~~~

Provider calls are **cumulative** from the start of the program. The first two requests do not increment it; only the two requests with valid CSRF reach `authenticate`.

## 14. When Only Real Browsers Fail While MockMvc Passes

### 14.1. Cookie/Session Lost or Changed

Scenario:
1. Browser loads `/login` form and token in session A.
2. POST hits replica B which does not share session A.
3. Expected token on B is missing or different.
4. `CsrfFilter` rejects before the provider.

Fixes:
- Spring Session with a shared repository or proper session affinity.
- Verify `JSESSIONID` is actually sent back with matching hostname and path.
- Verify cookie `Secure`, `SameSite`, `Domain`, `Path`, expiry.
- Never cache HTML forms containing CSRF tokens on a CDN across users.
- Never log raw cookies/tokens to analyze.

### 14.2. `fetch`/SPA Missing Credentials

With a same-origin frontend, `fetch` can use `credentials: "same-origin"`:

~~~javascript
await fetch("/login", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type":
      "application/x-www-form-urlencoded;charset=UTF-8"
  },
  body: new URLSearchParams({
    username: usernameFromForm,
    password: passwordFromForm,
    _csrf: maskedTokenFromTrustedPage
  })
});
~~~

This is an **illustrative JavaScript snippet**, assuming the token was rendered properly for the active session. Never hardcode tokens or pass another session's value.

For cross-origin requests, check `credentials: "include"`, CORS allowing **specific origins** with credentials, cookie policies, and matching CSRF proof. Never use wildcard CORS or disable CSRF to "fix" cookie bugs.

### 14.3. Does `SameSite` Replace CSRF?

`SameSite=Lax/Strict` cookies offer added defense, yet "same-site" does not equal "same-origin". Subdomains on the same site, redirects, browser differences, XSS, or other ambient credentials can alter the threat model. For browser-session apps, CSRF tokens remain a core protection while `SameSite` is **defense in depth**.

### 14.4. Wrong Header Name

The header name depends on the repository:
- `HttpSessionCsrfTokenRepository` usually uses `X-CSRF-TOKEN`.
- `CookieCsrfTokenRepository` usually uses `X-XSRF-TOKEN`.

Do not copy a frontend stack's default and assume the backend expects the same header. Read `CsrfToken.getHeaderName()` or configure the repository/handler explicitly.

## 15. CORS and CSRF Differ

| Mechanism | What It Checks | Failure |
|---|---|---|
| CORS | Which origins may perform/read certain cross-origin JS requests | Preflight/response blocked in browser |
| CSRF | Does an unsafe request carry context-valid proof? | Usually 403 at `CsrfFilter` |
| Authentication | Are credentials/tokens valid? | Login error, 401, or flow-specific |
| Authorization | Does the principal have permission on the resource? | 403 after authentication/checks |

An `OPTIONS` preflight can be blocked by CORS **before the login POST is even sent**, which is completely different from a POST reaching the backend without CSRF.

CORS does not replace CSRF: even when the browser stops JavaScript from reading responses, HTML forms and automatic credential attachment can still have side effects in some scenarios.

## 16. Multiple `SecurityFilterChain`s and Custom Login Paths

An app may configure:

~~~java
http.formLogin(form -> form
        .loginPage("/sign-in")
        .loginProcessingUrl("/auth/submit")
        .permitAll());
~~~

Then `GET /sign-in` is the login page **the app must render**, while `POST /auth/submit` is the processing endpoint. Changing only `loginPage` while the form still POSTs to `/login` breaks alignment.

With multiple chains, `FilterChainProxy` picks **the first matching chain** by order/matcher. Filter-provided endpoints (such as `POST /login`) exist only inside the chain holding that filter. If `/api/login` enters a Resource Server chain ahead of the form-login chain, there is no automatic reason for the later chain's `UsernamePasswordAuthenticationFilter` to run.

To diagnose:
1. Identify `@Order`, `securityMatcher`, and paths of each chain.
2. Check whether the selected chain includes `CsrfFilter`.
3. Check whether the selected chain includes `UsernamePasswordAuthenticationFilter`.
4. Confirm `loginProcessingUrl` falls within the right matcher.
5. Do not add `permitAll` or drop CSRF on another chain before knowing which chain is selected.

**A 403 response may come from CSRF on the selected chain rather than the provider in the chain you are debugging.**

## 17. Can You Disable CSRF as a Quick Fix?

**Never disable CSRF globally on browser form-login/session applications.**

Example to avoid:

~~~java
// Never use this to fix POST /login errors in browser applications:
http.csrf(csrf -> csrf.disable());
~~~

It may make a previously 403 POST "able to log in", yet it **removes login CSRF protection** and weakens all other unsafe requests.

A genuinely stateless API that authenticates **solely** via a client-supplied bearer token in the `Authorization` header and uses no ambient browser credentials may not need CSRF on those specific routes. Even then, you must:
- evaluate whether the API accepts cookies/sessions/HTTP Basic/client certificates;
- separate routes/chains cleanly;
- use a very narrow `csrf.ignoringRequestMatchers` backed by a security decision;
- test that no cookie-authenticated path was accidentally exempted;
- re-evaluate if adding refresh-token cookies, BFF/SPA sessions, or SSO.

**`SessionCreationPolicy.STATELESS` does not by itself prove there is no CSRF risk** if the endpoint still accepts credentials attached automatically by browsers.

## 18. Safe Logging and Observability During Investigation

Fields safe to record:
- UTC timestamp, request ID, method, path, and selected chain;
- `result=CSRF_REJECTED`, `AUTH_BAD_CREDENTIALS`, `AUTH_SUCCESS`;
- exception type `MissingCsrfTokenException` / `InvalidCsrfTokenException`;
- `csrf_field_present`, `csrf_header_present`, `session_present` as **booleans**;
- backend node/replica, proxy path, frontend build version;
- 403 rate on login POST before/after deploy, auth failure rate when CSRF passes;
- test provider call counts and correlation IDs.

**Never log:** raw passwords, raw CSRF tokens, `Authorization` headers, `Cookie`/`JSESSIONID`, full POST bodies, bearer tokens, session IDs, or unnecessary PII. If enabling DEBUG/TRACE, time-box it and restrict read access.

CSRF errors are sometimes displayed as "password incorrect" by custom UIs. Logging/monitoring must distinguish the failing layer so support never tells users to reset passwords unnecessarily.

## 19. Operational Test Matrix

| Case | Expectation |
|---|---|
| `POST /login` missing CSRF, right password | 403, `providerCalls=0` |
| `POST /login` missing CSRF, wrong password | 403, `providerCalls=0` |
| `POST /login` invalid CSRF, right password | 403, `providerCalls=0` |
| `POST /login` valid CSRF, right password | Authentication success |
| `POST /login` valid CSRF, wrong password | Authentication failure |
| `GET /login` anonymous | Form/token rendered |
| `@WithMockUser` + POST without CSRF | Still blocked by CSRF |
| `formLogin()` MockMvc builder | Includes valid CSRF automatically |
| Form from session A, POST in session B | Rejected in session repository model |
| Session expired while HTML form is stale | Requires fresh token/form |
| SPA post-login uses cleared token | Rejected until token refreshed |
| SPA raw header with matching handler | Passes CSRF filter |
| SPA raw header into masked-only handler | Rejected |
| Wrong cookie `SameSite/Secure/Path` | Browser may withhold session |
| Two replicas not sharing `HttpSession` | Token mismatch/missing |
| CORS preflight fails | Distinguished from POST CSRF failure |
| Custom `loginProcessingUrl` | Form action targets exact URL |
| Multiple chain ordering | Right filter chain selected |
| Form submits JSON to default form login | Never assume provider parses JSON automatically |
| `POST /logout` without CSRF | Blocked per policy |
| Stateless bearer-only API | Route-level CSRF policy per threat model |
| Test/prod logs | Contain no raw credentials or session tokens |

A real CSRF test must **keep the security filter chain enabled**. With `@AutoConfigureMockMvc(addFilters=false)`, tests can report false "success" because all security filters were bypassed.

## 20. Common Remediation Mistakes

1. Disabling CSRF system-wide to make `POST /login` work.
2. Adding `permitAll("/login")` and assuming tokens are no longer needed.
3. Editing `PasswordEncoder` when the provider was never called once.
4. Turning login submission into GET to avoid CSRF.
5. Logging raw tokens/passwords/sessions to compare.
6. Setting `SameSite=None` cookies without evaluating HTTPS and cross-origin trust.
7. Retaining an old token after login/logout and trying to reuse it.
8. Enabling `CookieCsrfTokenRepository` for an SPA without checking the XOR request handler.
9. Confusing the `formLogin()` test builder with a raw POST lacking CSRF.
10. Turning off MockMvc security filters so tests pass.
11. Forgetting cookie/session affinity in a cluster.
12. Debugging the wrong `SecurityFilterChain` due to multiple matchers.
13. Treating every 403 as a CSRF bug.
14. Treating CORS and CSRF as the same mechanism.
15. Trusting client-supplied forwarded headers.
16. Caching HTML login forms/tokens across all users.
17. Letting clients receive CSRF tokens from external sources or other users.
18. Dropping CSRF on password changes, account resets, and sensitive account actions.
19. Thinking CSRF failures must go through `AuthenticationFailureHandler`.
20. Assuming `InvalidCsrfTokenException` always means the token field was absent.
21. Assuming the JWT verifier ran when `CsrfFilter` blocked the request earlier.
22. Failing to verify client request method/path/encoding.

## 21. Incident Handling Checklist

- [ ] Confirm method/URL and `loginProcessingUrl`.
- [ ] Identify `SecurityFilterChain` and order of `CsrfFilter` relative to login filter.
- [ ] Confirm CSRF failure via exception/diagnostics or controlled test.
- [ ] `GET /login` renders `_csrf` and POST submits it with the matching session.
- [ ] Cookie/session has right `Secure`/`SameSite`/`Domain`/`Path`/expiry.
- [ ] Thymeleaf/form neither omits nor duplicates the token.
- [ ] SPA handles raw vs masked tokens with matching handler and repository.
- [ ] SPA refreshes token after authentication/logout when required.
- [ ] CORS/credentials/proxies configured properly without dangerous wildcards.
- [ ] Test missing, invalid, and valid CSRF for both right and wrong passwords.
- [ ] Provider counter/breakpoint confirms CSRF failure occurs **before** provider.
- [ ] Bad password with valid CSRF is reported by the authentication flow.
- [ ] Do not disable CSRF globally or turn off MockMvc filters.
- [ ] Test cluster/session store and real browsers.
- [ ] Never log raw passwords, tokens, cookies, or session IDs.
- [ ] Add a CI regression test for pre-provider CSRF failure.

## 22. Conclusion

**"Right password yet POST login returns 403 and the provider is never called"** matches `CsrfFilter` rejecting the request before authentication. To confirm, inspect the selected security chain, CSRF exception, token repository, request handler, and cookie/session; compare against a valid-CSRF request and count provider invocations.

~~~text
POST /login
    → right selected SecurityFilterChain?
    → CsrfFilter: token/session/handler valid?
          ├── No  → 403, providerCalls=0
          └── Yes → UsernamePasswordAuthenticationFilter
                        → AuthenticationManager
                        → AuthenticationProvider
                              ├── wrong password → auth failure
                              └── right password → auth success
~~~

**Fix the CSRF-proof delivery and session lifecycle; do not "fix" by disabling the protection layer.** With Spring Security 6, pay special attention to deferred loading, XOR masked tokens, and SPAs needing fresh tokens after login/logout.

## 23. References

1. [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): `CsrfFilter`, repositories, request handlers, login CSRF, SPAs.
2. [Spring Security 6.5 — Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): filter order, `FilterChainProxy`, selected chain.
3. [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): `UsernamePasswordAuthenticationFilter` and rendering form tokens.
4. [Spring Security 6.5 — Form Login MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html): `formLogin` builder automatically adds CSRF tokens.
5. [Spring Security 6.5 — SecurityMockMvcRequestBuilders API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestBuilders.html): request builders, CSRF.
6. [Spring Security 6.5 — CSRF Exceptions API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/package-summary.html): missing/invalid CSRF.
7. [Spring Security 6.5 — Multiple Filter Chains](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): `SecurityFilterChain` matchers/endpoint scoping.
8. [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer tokens, `SameSite`, and defenses.
9. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session/cookie security and invalidation.
