# Handling Missing, Invalid, or Expired CSRF Tokens and Returning Proper Error Responses

> **Context:** Spring Security **Reactive/WebFlux**, Spring Framework 6.x, Java 17+; examples use Spring Boot 3.3.x and Spring Security 6.3.x to study the APIs. The focus is detecting write requests with a missing CSRF token, a mismatched token, or a token invalidated after session expiration/logout, and returning clear error responses **without weakening CSRF protection**. Before production deployment, choose a supported Spring release and apply security patches.

## 1. What is CSRF and why do you see HTTP 403?

**Cross-Site Request Forgery (CSRF)** occurs when a user's browser automatically carries existing credentials (such as a session cookie) to a server where the victim is logged in, while another page tries to trigger an action on the user's behalf. To defend against this attack class, applications require an unpredictable, app-issued **CSRF token** that the browser must place into state-changing requests in a location **not auto-sent by the browser like cookies**.

```text
Browser with existing session cookie                WebFlux server
  |
  | GET /api/csrf  -------------------------------> CsrfWebFilter
  |                          loads/generates expected CSRF token in WebSession
  | <---------------------------------------------- {headerName, token}
  |                                                 Set-Cookie: SESSION=...
  |
  | POST /api/actions
  | Cookie: SESSION=...
  | X-CSRF-TOKEN: <received token>  --------------> compares actual token
  |                             +-- match --------> authorization -> controller
  |                             +-- missing/wrong -> 403; DOES NOT run action
```

**Session cookies** and **CSRF tokens** are two distinct artifacts:

- The `SESSION` cookie (WebFlux default, configurable) typically holds a **session ID** so the server can locate session data. Browsers attach cookies automatically when Domain/Path/SameSite rules allow.
- The CSRF token is returned by the server in a form or a response readable by trusted same-origin scripts; the client sends it back via the `X-CSRF-TOKEN` header or `_csrf` form field as needed.
- A CSRF token is **not** an access token, JWT, API key, password, or proof of user login. Tokens can be issued to unauthenticated visitors to protect login forms and pre-login requests.
- With the default `WebSessionServerCsrfTokenRepository`, the expected token is bound to the server-side `WebSession`. There is no guarantee the same token stays valid after the session is lost or changed.

### Safe HTTP principle

Spring Security's default CSRF protection applies primarily to **unsafe methods** such as `POST`, `PUT`, `PATCH`, and `DELETE`. `GET`, `HEAD`, `OPTIONS`, and `TRACE` must be kept strictly **read-only** by the application. If `GET /delete-account` deletes data, being treated as a safe method breaks the protection premise.

**CORS does not replace CSRF.** Browsers can still *send* cross-site requests even when CORS blocks JavaScript from *reading* responses. `SameSite` is a useful defense layer, yet does not replace threat modeling and anti-CSRF tokens.

## 2. Three cases to handle

| Scenario | Symptom | Typical cause | Safe outcome |
|---|---|---|---|
| **Missing token** | POST has session cookie yet lacks `X-CSRF-TOKEN`/`_csrf` | Form omitted hidden input, frontend didn't bootstrap token, fetch omitted header | **403**; do not run write operation |
| **Wrong token** | Header/token present yet mismatches expected token | Token from another tab/session; corrupted/altered value; wrong XOR decoding | **403**; do not run write operation |
| **Stale/"expired" token** | Token was previously valid, then fails verification | `WebSession` expired/invalidated, logout/login changed state, store refresh/redeploy, app rotation strategy | **403** when CSRF is invalid; do not auto-replay request |

The word **"expired" must be understood accurately**: with default token storage in `WebSession`, there is no separate per-token expiration timer purely for being a CSRF token. In practice, a missing session or changed expected token causes the old token to mismatch. Only if an app writes a custom repository with its own TTL can one speak of token-specific expiration under that design.

### Can the three reasons be distinguished from the exception alone?

In Spring Security **Servlet**, documentation mentions `org.springframework.security.web.csrf.MissingCsrfTokenException` and `InvalidCsrfTokenException`. **Do not confuse them with WebFlux.** In the reactive stack there is `org.springframework.security.web.server.csrf.CsrfException`; it is a subtype of `AccessDeniedException` used for both missing and invalid tokens. The default API **does not promise** distinct public error codes for "missing header", "wrong header", and "session expired".

A stale token after session expiration can look identical to a wrong token. If the app needs detailed internal metrics, design safe observability backed by controlled state and explicit policy; **never parse exception message strings to infer expiration**, and never let clients self-declare "token expired" via headers.

**Recommended policy:** return HTTP **403** with a uniform JSON code `csrf_rejected` for all three cases. Never return raw expected/actual tokens, session IDs, exception stack traces, or token-generation algorithms.

## 3. CsrfWebFilter flow in Spring WebFlux

Spring Security WebFlux implements CSRF via:

- `org.springframework.security.web.server.csrf.CsrfWebFilter`: WebFilter performing verification.
- `ServerCsrfTokenRepository`: saves/reads expected tokens.
- `WebSessionServerCsrfTokenRepository`: **default** implementation storing tokens in `WebSession`.
- `CookieServerCsrfTokenRepository`: option when frontend JavaScript needs to read tokens in the `XSRF-TOKEN` cookie.
- `ServerCsrfTokenRequestHandler`: exposes tokens on request attributes and resolves client-submitted tokens.
- `XorServerCsrfTokenRequestAttributeHandler`: default handler since Spring Security **6.0**, masking tokens to mitigate BREACH leaks on compressed responses.
- `ServerAccessDeniedHandler`: handler receiving CSRF errors rejected by the filter.

Diagram:

```text
Request enters SecurityWebFilterChain
          |
          v
      CsrfWebFilter
          |
          +--> exposes Mono<CsrfToken> on exchange attribute
          |         (token may be loaded/generated lazily)
          |
          +--> does method require CSRF protection?
          |        |
          |        +-- no (GET, HEAD, OPTIONS, TRACE by default)
          |        |         -> proceed to downstream filters/handlers
          |        |
          |        +-- yes (POST/PUT/PATCH/DELETE)
          |                  |
          |                  +-- repository supplies expected token
          |                  +-- request handler reads actual token
          |                  +-- compare per matching mechanism
          |                          |
          |                          +-- valid -> proceed
          |                          +-- invalid/missing
          |                                 -> CsrfException
          |                                 -> CSRF-specific accessDeniedHandler
          |                                 -> HTTP 403
          |
          v
    Authorization / controller (only if request passes filter)
```

**Never equate a CSRF 403 with a missing-role 403.** They share the same HTTP status code, yet may warrant different JSON codes (`csrf_rejected` vs. `access_denied`). A request missing a CSRF token can be blocked even if the URL is `permitAll()` or the caller holds `ROLE_ADMIN`. `401` (unauthenticated) and `403` (CSRF) can also surface differently depending on filter ordering and request state; **never force all CSRF errors into 401 or login redirects**.

### Common pitfall: the CSRF handler differs from the general access-denied handler

In WebFlux, there are two places to configure access denied:

```java
// CONFIG FRAGMENT, without full class/imports
http
    .csrf(csrf -> csrf
        .accessDeniedHandler(csrfDeniedHandler))
    .exceptionHandling(errors -> errors
        .accessDeniedHandler(generalDeniedHandler));
```

`csrf.accessDeniedHandler(...)` handles responses when `CsrfWebFilter` detects an invalid token. `exceptionHandling(...accessDeniedHandler(...))` handles authorization rejections. **Configuring `exceptionHandling` alone does not format CSRF errors**, because the CSRF filter has its own handler. The runnable example in Section 7 configures both for a clear API contract.

## 4. Choosing the response: 403, JSON, or HTML page?

### JSON API

A clean, SPA/mobile-friendly contract is `application/problem+json` per RFC 9457:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "CSRF validation failed",
  "code": "csrf_rejected"
}
```

`code` is an application-defined extension member. `type: about:blank` and `title: Forbidden` align with HTTP 403 semantics. The frontend can inspect `code` to guide the user to reload the form or refresh the CSRF token **via a safe GET**, rather than guessing from HTML error pages.

Why **not** return `419 Page Expired` or `440 Login Timeout` by default? Those are non-standard HTTP status codes; another framework may use them by convention, whereas Spring Security WebFlux uses **403 Forbidden** on CSRF failure by default. If an organization picks a custom code, it needs a clear client/proxy/monitoring contract; never label every 403 as "expired".

### HTML web pages

For server-rendered forms, you can display a **403** message page: "Your session or form security token is no longer valid. Please reopen the form and submit again." You may provide a `GET /form` link to fetch a fresh token. Never automatically redirect a CSRF-failed **POST** to login and replay the write payload: clients may misinterpret whether the operation ran, increasing duplicate-submission risk.

If choosing to redirect to a helper page via GET, still keep the failed action's status clear; never turn an auth/CSRF error into a 200 success. For APIs, JSON 403 is cleaner and more consistent than HTML redirects.

### Prefer helpful metadata without leaking internals

Avoid bodies like:

```json
{
  "error": "Expected token 3cb... but got header a71...",
  "sessionId": "secret-session-id"
}
```

This response leaks the protection mechanism itself. For debugging, log only non-sensitive metadata: timestamp, route template, HTTP method, `csrf_rejected` code, correlation ID, environment, and system state (no raw cookies/tokens/headers or query secrets).

## 5. When can a token become invalid?

### 5.1 WebSession expiration

`WebSessionServerCsrfTokenRepository` uses server-side sessions. The browser may still carry a `SESSION` cookie while the server has removed/expired the session (idle timeout, restart with an in-memory store, explicit invalidation). The CSRF header remaining in an old tab no longer matches the new token loaded/generated for the current session.

**Handling flow:** treat the rejected POST as unexecuted, guide the user to a **safe GET** to load a new form/token; if the login session was lost, require re-authentication through a valid mechanism. Never treat the mere presence of a `SESSION` cookie as proof of active authentication.

### 5.2 Logout, login, session ID, and token rotation

Logout typically clears `WebSession`/security state; tokens tied to the old session may be destroyed along with it. Upon login or privilege elevation, the system may rotate session IDs or refresh tokens per configured handlers. **Never assume every authentication event produces the exact same sequence across all chains**, especially across Basic/JWT/form login and custom repositories.

If an SPA keeps an old token in memory after logout/login, the next state-changing request may return 403. Re-bootstrap the token after authentication state transitions and ensure the new session cookie is saved before sending other operations.

### 5.3 Multiple browser tabs and race conditions

- One tab opens a form before session expiration; the user returns minutes later, and the old token is no longer valid.
- One tab logs out or changes session while another tab still holds the old token.
- Two concurrent requests can hit a session rotation/invalidation race; test the behavior explicitly.
- An SPA issuing concurrent requests that auto-refresh tokens on 403 can trigger a "retry storm" or duplicate transactions if code is not synchronized properly.

Never implement "on any 403, refresh and auto-retry". A 403 may be **missing authorization**, unrelated to CSRF. Even on `csrf_rejected`, financial/write operations must not be blindly replayed. Use idempotency keys and user confirmation when business logic requires it.

### 5.4 Changing the CSRF token repository

With `CookieServerCsrfTokenRepository`, cookie `XSRF-TOKEN` and header `X-XSRF-TOKEN` are the common defaults. When JavaScript needs to read the cookie, `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` is the documented option, yet exposes the token to JS reads (an XSS trade-off). **Never switch to the cookie repository just to "fix CSRF 403"** without evaluating SameSite, origin, BREACH masking, and client request handlers.

**Spring Security 6+ warning:** the XOR request handler is enabled by default. Raw tokens read by JavaScript from a cookie may **fail to decode properly** if sent straight in a header under a config incompatible with the XOR handler. Use a compatible SPA/request-handler strategy and test against your exact version. The demo below keeps **default `WebSession` repository + XOR**, without stripping BREACH protection.

## 6. Distinguishing CSRF failures from authentication and authorization

| Request scenario | Typical expected HTTP status | Handling |
|---|---|---|
| Unauthenticated `GET /api/csrf` | 200 if endpoint is public | Returns token for client to prepare forms/APIs; does not mean user is logged in |
| `GET /api/private` without credentials | 401 | Require authentication per protocol |
| `POST /api/actions` with valid Basic yet missing CSRF | 403 + `csrf_rejected` | Do not execute action; fetch fresh token via GET |
| `POST /api/actions` with valid Basic and wrong token | 403 + `csrf_rejected` | Never guess/disclose expected token |
| `POST /api/actions` with valid Basic and invalidated-session token | 403 + `csrf_rejected` | Re-bootstrap session/token; may require re-login |
| `POST /api/actions` with valid token yet unauthenticated | 401 | CSRF token never becomes a credential |
| `POST /api/admin` with valid token, user lacks ADMIN | 403 + `access_denied` | Do not treat as expired CSRF |
| GET request without CSRF token | Not blocked by CSRF solely for missing token | Still subject to authentication/authorization |
| POST fails validation after passing CSRF | 400 if business/validation returns 400 | Never misreport as a CSRF error |

These statuses reflect the **demo configuration's conventions**, not a universal statement about filter ordering in every app. On a request **missing both authentication and CSRF**, CSRF may reject first and the caller sees **403** instead of 401. Test each condition independently, especially when debugging client bug reports.

### Never "treat" a security error by removing security

Three common wrong fixes:

```java
// Never do this in a cookie-session web app to "fix" 403:
csrf.disable();

// Never make every route public:
.anyExchange().permitAll();

// Never let a POST missing a token continue processing on error:
// dangerous pseudo-code: catch (CsrfException) { continueChain(); }
```

These are **anti-pattern snippets**, not runnable configs. Find the root cause instead: token never issued, JavaScript forgot the header, session expired, incompatible masking, cookie not sent, reverse proxy domain/path mismatch, or login/logout needing re-bootstrap.

## 7. Complete Spring Boot WebFlux demo: JSON 403 errors and stale tokens

This example uses **HTTP Basic + WebSession-based CSRF** so both can be verified independently: HTTP Basic verifies identity, while the session cookie backs the expected CSRF token. Basic auth never turns a CSRF token into a password. One public GET endpoint issues tokens, two POSTs require login + token, and one POST invalidates the session to simulate **stale tokens losing validity** after session destruction.

**Run example credentials only on localhost/HTTPS.** Passwords in code are strictly learning data. Production projects use patched framework versions, HTTPS, and proper account/session management.

### 7.1 Structure

```text
webflux-csrf-errors/
  settings.gradle
  build.gradle
  src/main/java/example/csrf/CsrfApplication.java
  src/main/java/example/csrf/SecurityConfiguration.java
  src/main/java/example/csrf/ApiController.java
  src/test/java/example/csrf/CsrfFlowTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-csrf-errors'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.csrf'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Never add Servlet's `spring-boot-starter-web`. This lesson uses WebFlux's `ServerHttpSecurity`/`SecurityWebFilterChain` and `CsrfWebFilter`.

### 7.2 Application

**src/main/java/example/csrf/CsrfApplication.java**

```java
package example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfApplication.class, args);
    }
}
```

### 7.3 SecurityConfiguration: CSRF handler and authentication handler

**src/main/java/example/csrf/SecurityConfiguration.java**

```java
package example.csrf;

import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("dev-alice-only"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        ServerAuthenticationEntryPoint authEntry = (exchange, failure) ->
            problem(exchange, HttpStatus.UNAUTHORIZED, "authentication_required");

        ServerAccessDeniedHandler csrfDenied = (exchange, failure) ->
            problem(exchange, HttpStatus.FORBIDDEN, "csrf_rejected");

        ServerAccessDeniedHandler permissionDenied = (exchange, failure) ->
            problem(exchange, HttpStatus.FORBIDDEN, "access_denied");

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET,
                    "/api/csrf", "/api/status").permitAll()
                .pathMatchers(HttpMethod.POST,
                    "/api/actions", "/api/session/invalidate")
                    .authenticated()
                .anyExchange().denyAll())
            .httpBasic(basic ->
                basic.authenticationEntryPoint(authEntry))
            .formLogin(form -> form.disable())
            .csrf(csrf -> csrf
                // WebFlux already uses this repository type by default;
                // declared explicitly to show where expected tokens live.
                .csrfTokenRepository(
                    new WebSessionServerCsrfTokenRepository())
                .accessDeniedHandler(csrfDenied))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(authEntry)
                .accessDeniedHandler(permissionDenied))
            .build();
    }

    private static Mono<Void> problem(ServerWebExchange exchange,
                                      HttpStatus status,
                                      String code) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(
            MediaType.APPLICATION_PROBLEM_JSON);
        response.getHeaders().set(HttpHeaders.CACHE_CONTROL, "no-store");

        if (status == HttpStatus.UNAUTHORIZED) {
            response.getHeaders().set(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"training\"");
        }

        // Only fixed server-side codes are allowed.
        // Never output exception messages, session IDs, or tokens.
        String json = switch (code) {
            case "authentication_required" -> """
                {"type":"about:blank","title":"Unauthorized",
                 "status":401,"detail":"Authentication required",
                 "code":"authentication_required"}
                """;
            case "csrf_rejected" -> """
                {"type":"about:blank","title":"Forbidden",
                 "status":403,"detail":"CSRF validation failed",
                 "code":"csrf_rejected"}
                """;
            default -> """
                {"type":"about:blank","title":"Forbidden",
                 "status":403,"detail":"Access denied",
                 "code":"access_denied"}
                """;
        };

        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(bytes)));
    }
}
```

**Technical explanation:**

1. `@EnableWebFluxSecurity` + `SecurityWebFilterChain` is **reactive** configuration, not Servlet's `HttpSecurity`.
2. `GET /api/csrf` and `GET /api/status` are public; CSRF tokens can be issued to visitors. `POST /api/actions` and `POST /api/session/invalidate` require real authentication.
3. `httpBasic(...authenticationEntryPoint(...))` makes invalid Basic credentials return consistent 401 JSON instead of a different default response.
4. `csrf.csrfTokenRepository(new WebSessionServerCsrfTokenRepository())` stores expected tokens in `WebSession`. This explicitly illustrates **the default value** and does not have to be rewritten in production.
5. `csrf.accessDeniedHandler(csrfDenied)` guarantees **rejections from `CsrfWebFilter`** return status 403, `application/problem+json`, and code `csrf_rejected`.
6. `exceptionHandling(...accessDeniedHandler(permissionDenied))` returns code **`access_denied`** for general authorization errors, keeping them separate from CSRF.
7. `exceptionHandling(...authenticationEntryPoint(authEntry))` gives unauthenticated requests **401** with a Basic challenge. A CSRF token never bypasses login.
8. **Never disable CSRF**, never use `permitAll` on sensitive POSTs, and never fall back from errors to success actions.
9. JSON is built from fixed literals; never concatenate raw exceptions, user input, or tokens into the body, preventing leaks.
10. The demo intentionally **keeps Spring Security 6.x's default XOR request handler**. It supplies proper tokens for `GET /api/csrf` and resolves client-returned values. Never use `ServerCsrfTokenRequestAttributeHandler` to disable BREACH just to simplify a demo.

### 7.4 Controller: issuing tokens, recording simulated writes, invalidating sessions

**src/main/java/example/csrf/ApiController.java**

```java
package example.csrf;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;

import org.springframework.security.web.server.csrf.CsrfToken;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record CsrfView(String headerName, String token) {}
    public record Command(String action) {}
    public record ActionView(String status, int accepted) {}
    public record CounterView(int accepted) {}
    public record Ack(String status) {}

    private final AtomicInteger accepted = new AtomicInteger();

    @GetMapping("/api/csrf")
    public Mono<CsrfView> csrf(ServerWebExchange exchange) {
        // CsrfWebFilter exposes Mono<CsrfToken> on the request attribute.
        Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                "CSRF filter is not configured for this request"));
        }

        // Subscribe to token source: repository may generate/save
        // expected token into WebSession before returning the response.
        return token.map(value ->
            new CsrfView(value.getHeaderName(), value.getToken()));
    }

    @GetMapping("/api/status")
    public Mono<CounterView> status() {
        return Mono.just(new CounterView(accepted.get()));
    }

    @PostMapping("/api/actions")
    public Mono<ActionView> action(@RequestBody Command command) {
        if (command.action() == null || command.action().isBlank()) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "action must not be blank"));
        }

        // Count requests that genuinely passed CSRF/authorization filters.
        return Mono.fromSupplier(() ->
            new ActionView("accepted", accepted.incrementAndGet()));
    }

    @PostMapping("/api/session/invalidate")
    public Mono<Ack> invalidate(WebSession session) {
        // Invalidate session -> expected token stored in old session becomes invalid.
        return session.invalidate()
            .thenReturn(new Ack("session-invalidated"));
    }
}
```

**Never expose this CSRF token endpoint to the Internet without evaluating CORS and caching.** It is a same-origin application bootstrap endpoint: it returns tokens to trusted scripts on the same site and creates a session when tokens are generated. Restrict origins, disable caching, never put tokens into analytics/logs, and never enable wildcard CORS with credentials. In authenticated systems, the token does not represent login authority and must be guarded by appropriate same-origin/Origin policies.

Why `CounterView` exists: when a token is missing/wrong, `action()` **must not be invoked**. Reading the counter before and after rejected requests proves no business side effect occurred; this is purely a demo counter, not a database transaction.

### 7.5 Running the app and viewing error JSON

From the project directory (JDK 17+, Gradle compatible with Spring Boot 3.3, Maven repository access):

```bash
gradle bootRun
```

If a compatible Gradle Wrapper is present, use `./gradlew bootRun`; on Windows use `gradlew.bat bootRun`.

Test a request **missing the token**:

```bash
curl -i -X POST http://localhost:8080/api/actions \
  -H "Content-Type: application/json" \
  --data '{"action":"ping"}'
```

Expect HTTP **403** with `code: csrf_rejected`. The request above also lacks credentials, yet in a WebFlux setup with the CSRF filter, token errors may be handled before the login-required branch. **Never treat this 403 as meaning the user is logged in.**

To fetch a token and cookie for the same session, use an HTTP client supporting cookie jars (never copy real tokens into guides or logs). Conceptual flow:

```http
GET /api/csrf HTTP/1.1
Accept: application/json

HTTP/1.1 200 OK
Set-Cookie: SESSION=<opaque-session-id>; Path=/; HttpOnly; ...
Content-Type: application/json

{"headerName":"X-CSRF-TOKEN","token":"<masked-csrf-token>"}

POST /api/actions HTTP/1.1
Authorization: Basic <credentials>
Cookie: SESSION=<same-session-id>
Content-Type: application/json
X-CSRF-TOKEN: <masked-csrf-token>

{"action":"ping"}
```

All `<...>` values in the HTTP example are placeholders, **not credentials**. The token returned from GET is masked by the default handler; the client sends back the exact received value via the corresponding `headerName` and keeps the session cookie. **Never fabricate a token on the client by generating a UUID**, because the server needs a matching expected token in its repository.

Section 7.6 provides automated tests that genuinely read tokens from GET and cookies from responses without mocking tokens.

## 7.6. Integration testing with WebTestClient (real tokens and cookies)

The tests below use `RANDOM_PORT` rather than mocked security principals to verify the app's end-to-end HTTP flow: GET issuing tokens, POST with Basic/CSRF, POST with wrong token, invalidating the session, and re-sending the stale token. Do not use `mutateWith(csrf())` for tests proving real session/token behavior, since that test mutator simulates a valid token and does not substitute for session-expiration scenarios.

**src/test/java/example/csrf/CsrfFlowTest.java**

```java
package example.csrf;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CsrfFlowTest {

    @Autowired
    WebTestClient client;

    record SessionToken(String sessionId, String headerName,
                        String token) {}

    private SessionToken issueToken() {
        var result = client.get().uri("/api/csrf")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody(ApiController.CsrfView.class)
            .returnResult();

        var body = result.getResponseBody();
        assertNotNull(body);

        ResponseCookie session =
            result.getResponseCookies().getFirst("SESSION");
        assertNotNull(session);
        assertTrue(!session.getValue().isBlank());
        assertTrue(!body.token().isBlank());

        return new SessionToken(session.getValue(),
            body.headerName(), body.token());
    }

    @Test
    void safeGetDoesNotRequireCsrf() {
        client.get().uri("/api/status")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.accepted").exists();
    }

    @Test
    void missingTokenWithValidAuthenticationReturns403() {
        var issued = issueToken();

        client.post().uri("/api/actions")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.code").isEqualTo("csrf_rejected");
    }

    @Test
    void wrongTokenWithSameSessionReturns403() {
        var issued = issueToken();

        client.post().uri("/api/actions")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> {
                h.setBasicAuth("alice", "dev-alice-only");
                h.set(issued.headerName(), "definitely-wrong");
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("csrf_rejected");
    }

    @Test
    void correctTokenAndCredentialCanPerformAction() {
        var issued = issueToken();

        client.post().uri("/api/actions")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> {
                h.setBasicAuth("alice", "dev-alice-only");
                h.set(issued.headerName(), issued.token());
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("accepted");
    }

    @Test
    void csrfTokenDoesNotReplaceLoginCredential() {
        var issued = issueToken();

        client.post().uri("/api/actions")
            .cookie("SESSION", issued.sessionId())
            .header(issued.headerName(), issued.token())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody()
            .jsonPath("$.code")
            .isEqualTo("authentication_required");
    }

    @Test
    void tokenWithoutItsSessionIsRejected() {
        var issued = issueToken();

        // Server-issued token without the matching SESSION cookie.
        client.post().uri("/api/actions")
            .headers(h -> {
                h.setBasicAuth("alice", "dev-alice-only");
                h.set(issued.headerName(), issued.token());
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("csrf_rejected");
    }

    @Test
    void oldTokenAfterInvalidateIsRejectedAndFreshTokenWorks() {
        var old = issueToken();

        // Valid request intentionally invalidating WebSession.
        client.post().uri("/api/session/invalidate")
            .cookie("SESSION", old.sessionId())
            .headers(h -> {
                h.setBasicAuth("alice", "dev-alice-only");
                h.set(old.headerName(), old.token());
            })
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("session-invalidated");

        // Resending invalidated session's cookie/CSRF token -> 403.
        client.post().uri("/api/actions")
            .cookie("SESSION", old.sessionId())
            .headers(h -> {
                h.setBasicAuth("alice", "dev-alice-only");
                h.set(old.headerName(), old.token());
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("csrf_rejected");

        // Re-bootstrap token/session via safe GET.
        var fresh = issueToken();

        client.post().uri("/api/actions")
            .cookie("SESSION", fresh.sessionId())
            .headers(h -> {
                h.setBasicAuth("alice", "dev-alice-only");
                h.set(fresh.headerName(), fresh.token());
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void badBasicCredentialWithValidCsrfIs401() {
        var issued = issueToken();

        client.post().uri("/api/actions")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> {
                h.setBasicAuth("alice", "wrong-password");
                h.set(issued.headerName(), issued.token());
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody()
            .jsonPath("$.code")
            .isEqualTo("authentication_required");
    }
}
```

**8 test methods** designed to prove:

1. Safe GET requires no CSRF token.
2. Valid session and user yet **missing header** -> 403 `csrf_rejected`.
3. Submitted token has **wrong value** -> 403 `csrf_rejected`.
4. Valid token + credentials -> 200 and action accepted.
5. Valid token yet **unauthenticated** -> 401; CSRF does not replace credentials.
6. Valid token without its **matching session cookie** -> 403.
7. After `WebSession.invalidate()`, old token cannot be reused; fetching a new token via GET allows valid POST.
8. Wrong Basic password with valid CSRF -> 401; distinct from CSRF failure.

Run:

```bash
gradle test
```

These are **expected outcomes based on design and APIs**, not a claim that the build ran in the current environment. Any dependency/Gradle/Netty errors or real config differences must be checked in logs. The project uses the default single-process `WebSession` store and does not directly exercise real idle timeouts or multi-node interaction.

### 7.7. Quick testing with Spring Security Test's csrf() mutator

When you only want to verify that a POST route requires CSRF **without** testing the real cookie/token lifecycle, Spring Security Test provides a helper:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

// TEST FRAGMENT using WebTestClient configured with Spring Security Test:
client.mutateWith(csrf())
    .post().uri("/api/actions")
    .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
    .bodyValue(new ApiController.Command("ping"))
    .exchange()
    .expectStatus().isOk();
```

The import above can be written on one line for easier copying:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
```

Using `csrf()` requires the `spring-security-test` dependency and appropriate `WebTestClient` integration config, and the test mutator operates mainly against mock servers. Never use a **test-mocked** token to claim session expiry is handled properly in the real app; for that, use the real HTTP token+cookie test in Section 7.6. This is solely a supplemental test fragment requiring imported dependencies.

## 8. How should the frontend handle 403?

### Distinguishing by error code

API clients can inspect JSON status and `code`:

```text
response.status == 401:
    -> invalid authentication / sign-in required
    -> route user into login flow

response.status == 403 && body.code == "csrf_rejected":
    -> write request was rejected
    -> inform user the action was NOT performed
    -> fetch new token via GET /api/csrf (same-origin)
    -> ask user to resubmit or perform controlled retry

response.status == 403 && body.code == "access_denied":
    -> user lacks permission
    -> DO NOT repeatedly refresh CSRF tokens
```

### Client-side JavaScript pseudocode

```javascript
let csrf = null;

async function loadCsrf() {
  const response = await fetch("/api/csrf", {
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) throw new Error("Cannot fetch CSRF token");
  csrf = await response.json();
}

async function submitAction(action) {
  if (!csrf) await loadCsrf();

  const response = await fetch("/api/actions", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ action })
  });

  if (response.status === 403) {
    const problem = await response.json().catch(() => ({}));
    if (problem.code === "csrf_rejected") {
      csrf = null;
      // DO NOT automatically resend the write operation here.
      // You may call loadCsrf() to prepare for the next submission,
      // but you must inform the user the action was rejected.
      throw new Error("Session/CSRF token invalid; retry manually");
    }
  }

  if (response.status === 401) {
    throw new Error("Sign-in required");
  }

  if (!response.ok) throw new Error("Action rejected");
  return response.json();
}
```

The code above is a **client illustration**; production apps must handle accessibility/i18n, loading states, idempotency, network timeouts, and real authentication management. The demo API uses Basic auth so browsers may show a prompt; a real SPA may use cookie-based login/OIDC, requiring corresponding credential/CSRF strategies.

### Why not auto-retry POST?

- The prior request might have reached the backend in another ambiguous failure mode; never blindly retry all security or network errors.
- The user may have logged out or timed out; fresh login state must be verified.
- Money transfers or orders must never be replayed blindly. Only consider controlled retries when business logic supports idempotency keys and a safe retry contract.
- A 403 might be missing roles or a policy violation unrelated to CSRF.
- Resending the same old token after session loss will simply repeat 403.

## 9. Generating fresh tokens properly

### 9.1 For server-side HTML forms

The server can place `CsrfToken` into a hidden input, e.g. (illustrative dummy token):

```html
<form method="post" action="/account/update">
  <input type="hidden" name="_csrf" value="<token-from-server>">
  <input type="text" name="displayName">
  <button type="submit">Save</button>
</form>
```

`<token-from-server>` is a placeholder. With Spring Security WebFlux, tokens are normally supplied via exchange attributes or Thymeleaf integration, never hardcoded in HTML. After session expiration, re-render the form/issue a new GET to obtain a fresh token. **Never send CSRF tokens in URL query strings**, as they leak easily via logs, browser history, and referrers.

### 9.2 For JSON/AJAX

Use a same-origin `GET /api/csrf` where the backend returns header name and token; the frontend sends the matching header name. Default XOR behavior can cause **the token value emitted per response to differ** even when the expected raw token hasn't changed; never compare masked token strings across two GETs to infer the session changed.

### 9.3 For CookieServerCsrfTokenRepository

`CookieServerCsrfTokenRepository` supports JavaScript clients reading the `XSRF-TOKEN` cookie and sending `X-XSRF-TOKEN`. Yet when keeping the default XOR handler, configure a request handler compatible with how JS sends the raw cookie token; depending on version, coordinate mask/unmask handling and token bootstrapping after login/logout. Never copy a Servlet `CookieCsrfTokenRepository` snippet into WebFlux; interface/implementation names differ.

### 9.4 Never issue new tokens via a GET that mutates business state

A token-bootstrapping GET may start a `WebSession` (necessary technical state) but **must never execute business transactions**. Because GET is treated as a safe HTTP method, CSRF defense relies on GET/HEAD/OPTIONS/TRACE leaving business state unchanged.

## 10. Real-world pitfalls easily overlooked

### 10.1 Token is present yet still rejected

Common causes:

- Wrong header name: client sends `X-XSRF-TOKEN` while repo/response expects `X-CSRF-TOKEN`; use `getHeaderName()` or the matching contract.
- Wrong header value: client reads raw token from cookie while server expects an XOR-masked token per the default request handler.
- `SESSION` cookie not sent: domain, Path, SameSite, Secure, CORS credentials mismatch, or expired cookie.
- Expected token in `WebSession` changed/deleted: logout, session invalidation/timeout, lost session store on restart, or multi-node mismatch.
- Frontend cached an earlier user session's token in memory/localStorage without syncing after login/logout.
- Request sent `Content-Type: application/json` while token sat in a query/form field not read by the request handler as expected.
- Multiple `SecurityWebFilterChain` beans: route matched a chain with a different CSRF repository/request handler.
- `/api/csrf` endpoint never actually subscribed to `Mono<CsrfToken>`, so the expected token was never generated/saved before response completion.

Never "fix" this by putting all unsafe methods on the CSRF ignore list. Inspect actual requests/responses in DevTools with **token values redacted** when sharing logs or screenshots.

### 10.2 Session expiration can yield 401 or 403

A protected GET after session expiration may receive **401/login redirect** because identity is gone. Meanwhile a POST carrying the old cookie and old CSRF token may get **403** from `CsrfWebFilter` before authorization checks authentication. Thus clients cannot deduce from **every 403** that the session definitely expired. The safe design is returning `csrf_rejected` on failed CSRF checks, then re-bootstrapping/re-authenticating per flow if needed.

### 10.3 Does a CSRF token need its own expiration time?

Not necessarily. `WebSessionServerCsrfTokenRepository` binds the token to the session; `WebSession`'s idle timeout policy is a key factor. If your system requires separate rotation/TTL, implement it explicitly in the repository or session-management policy and test multi-tab synchronization; never invent "tokens expire after 30 minutes" when the framework makes no such guarantee.

### 10.4 Should you return HTTP 200 with error JSON?

**No.** Returning a real 403 lets clients, proxies, metrics, APM, and users recognize the action was blocked. `{"success":false}` with 200 misrepresents semantics and is easily mistaken for success by clients.

### 10.5 Should a CSRF-failed POST redirect to login?

Not by default. 302/303 may make the browser load the login page, yet erases the "action failed" signal and risks losing form data; redirecting neither fixes the token nor proves the session expired. HTML pages can return 403 with a GET link to reload the form, while APIs should return 403 JSON.

### 10.6 Should you print exception messages to inspect wrong tokens?

No. Some error messages may expose details about tokens/headers. Logging `exception.getMessage()` verbatim without review can leak tokens into logs. Use fixed structured metric codes, correlation IDs, route templates, and statuses. When deep diagnostics are needed in controlled environments, thoroughly redact tokens and session IDs.

### 10.7 Multiple instances and session stores

If an app uses `InMemoryWebSessionStore` across multiple pods without shared storage, cookies may point to sessions known only to pod A; requests routed to pod B can fail CSRF. When scaling, evaluate Spring Session Redis/reactive repositories, and configure session TTLs, serialization, and consistency. Sticky sessions are only a stopgap and do not cure session loss on pod restarts.

### 10.8 Basic, JWT, and browser cookies

CSRF is riskiest when browsers **auto-send credentials** to a site by context (cookies/sessions, some forms of browser-managed auth). For APIs using bearer tokens deliberately attached in `Authorization` by JavaScript, the CSRF threat model can differ. Only consider exempting CSRF on chains that are truly stateless and use zero auto-sent cookies/credentials, after auditing the entire API. Never disable by default just because routes start with `/api`.

## 11. Symptom-based fixes

| Symptom | What to check | Solution |
|---|---|---|
| Every POST returns 403 right after page load | Did GET/bootstrap fetch the token? Did client send the right header/field? | Render token in form or call GET token endpoint and send header |
| First POST works; after long idle returns 403 | `WebSession` timeout, stale cookie, logout in another tab? | Do not replay POST; prompt to reload form/token and re-login if needed |
| `XSRF-TOKEN` cookie present yet header still 403 | Do cookie repo + XOR request handler match how client sends raw tokens? | Check Spring Security version and configure SPA/request handler |
| POST 403 even though user is logged in with right role | Might be CSRF rather than role | Separate `csrf_rejected` from `access_denied` via handlers and test |
| POST without token returns 200 | CSRF disabled/ignored, wrong security chain, or GET mutating data? | Restore CSRF filter and ensure unsafe routes hit the protected chain |
| 403 when calling from another frontend domain | Cookie `SameSite`/`Secure`, CORS credentials, Origin, CSRF header | Configure CORS + CSRF tokens properly; no open wildcards |
| Token from `/csrf` still yields 403 when sent | Same session cookie sent? Proper token masking? | Keep the same cookie jar and use server-issued tokens |
| 403 after logout then login | Session/token not re-bootstrapped | Clear client token cache; GET fresh token |
| 403 on PUT/PATCH/DELETE | These methods are also unsafe | Send token on all unsafe methods required by policy |
| Cannot distinguish missing authority from CSRF | Single generic 403 from all filters | Configure separate `csrf.accessDeniedHandler` and `exceptionHandling.accessDeniedHandler` |
| `mutateWith(csrf())` tests PASS yet prod fails | Tests bypassed real session-cookie exchange | Write real token+cookie integration tests per Section 7.6 |
| Intermittent errors behind load balancer | Unshared `WebSession` store or mismatched timeouts | Use shared reactive session store, sync TTLs, monitor |

## 12. Implementation and security testing checklist

1. Confirm **WebFlux/reactive** usage (`CsrfWebFilter`, `ServerHttpSecurity`), avoiding Servlet `CsrfFilter`/`HttpSecurity`.
2. Keep CSRF enabled for all state-changing requests in web apps using browser-managed credentials.
3. Ensure GET/HEAD/OPTIONS/TRACE cause zero business side effects.
4. Choose repository: default `WebSession` or `CookieServerCsrfTokenRepository` for SPAs; configure request handler compatible with XOR and version.
5. If issuing tokens via GET, **subscribe** to `Mono<CsrfToken>` and emit the matching cookie/session; enforce same-origin/CORS and `no-store`.
6. For unsafe methods, send the token in a header or form parameter, **never relying solely on auto-sent cookies**.
7. Return **403** with generic error code `csrf_rejected` for missing/wrong/stale tokens; never disclose tokens/sessions.
8. Keep distinct codes for `401 authentication_required` and `403 access_denied` from roles/business rules.
9. Never auto-replay POST/PUT/DELETE on CSRF errors; prompt to fetch a fresh token and resubmit intentionally.
10. Test idle timeouts, logout/login, session ID rotation, multi-tab behavior, refreshes, and multi-node session stores.
11. Run tests with real tokens and real cookies; include missing token, wrong token, absent cookie, invalidated session, and missing/wrong auth.
12. Verify CSRF/CORS, `SameSite`, `Secure`, `HttpOnly`, TLS reverse proxies, and per-chain custom exception handling.
13. Never write raw tokens, session IDs, or `Authorization` headers to logs/telemetry; use non-sensitive metric/trace IDs.
14. Exempt CSRF only on routes whose analyzed threat model confirms zero browser-auto-sent credentials.
15. Upgrade Spring Security to supported patched releases, re-verify APIs after major/minor bumps, and test in realistic environments.

## 13. Self-practice exercises

1. Run the project and send `POST /api/actions` with valid Basic auth yet **without** `X-CSRF-TOKEN`. Why does 403 occur before the controller?
2. Call `GET /api/csrf`; save the `SESSION` cookie and token. Send a POST with both cookie and token and confirm 200.
3. Alter a single character in the token when sending POST. Explain why the server must never "correct" a client's token.
4. Use the received token while **omitting the `SESSION` cookie**. Why does that token fail to prove the current request belongs to the session that issued it?
5. Call a valid `POST /api/session/invalidate` and reuse the old token. Why does this simulate an invalidated token rather than proving tokens have a standalone TTL?
6. Replace `httpBasic` with real form-login/sessions and write browser tests for login GET, login POST CSRF, logout, and stale-tab requests. Distinguish 401, 302, and 403.
7. Switch the repository to `XSRF-TOKEN` cookies and test `X-XSRF-TOKEN` rules with the XOR request handler. Explain the risk of disabling `HttpOnly`.
8. Write an integration test verifying **the counter does not increment** when a POST has a missing/wrong CSRF token.
9. Create a user with `ROLE_USER` but not `ROLE_ADMIN`, add an admin POST route, and test 403 `access_denied` with valid CSRF.
10. Design UI handling when a user spends 30 minutes filling a form, the session expires, and they click Save. Which message avoids confusion? When must re-login be requested?
11. Test changing the session cookie name or running two pods without a shared `WebSessionStore`. What symptoms appear and how do you fix them?
12. Distinguish CORS blocked, CSRF rejected, invalid Basic credentials, and authorization denied. Why is looking at a single 403 insufficient?

## Conclusion

In Spring Security **WebFlux**, `CsrfWebFilter` validates CSRF tokens on **unsafe** requests, and the default `WebSessionServerCsrfTokenRepository` stores expected tokens in `WebSession`. **Missing tokens, wrong tokens, and stale tokens after session invalidation must all be rejected**, typically with HTTP **403**. Never confuse reactive `CsrfException` with Servlet exceptions or label errors "expired" without evidence of a dedicated TTL. APIs should return `application/problem+json` with generic code `csrf_rejected`, distinct from `authentication_required` (401) and `access_denied` (403). When clients hit an error, **never disable CSRF and never auto-replay POSTs**; instead, bootstrap a new token/session via a safe GET, require re-authentication when needed, and let users resubmit actions through a controlled flow.

## Official References to Verify by Version

1. Spring Security 6.5 — CSRF for WebFlux, WebSession repository, request handler, and session timeout: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
2. Spring Security 6.3.8 — `CsrfWebFilter` and `setAccessDeniedHandler`: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/web/server/csrf/CsrfWebFilter.html
3. Spring Security 6.3.8 — `XorServerCsrfTokenRequestAttributeHandler`: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html
4. Spring Security 6.5 — `ServerHttpSecurity.CsrfSpec.accessDeniedHandler`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.CsrfSpec.html
5. Spring Security 6.3.8 — Reactive `CsrfException`: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/web/server/csrf/CsrfException.html
6. Spring Security — Reactive WebTestClient CSRF testing: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
7. Spring Security — CSRF conceptual reference, synchronizer tokens, and safe methods: https://docs.spring.io/spring-security/reference/features/exploits/csrf.html
8. Spring Framework — WebSession API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebSession.html
9. RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
