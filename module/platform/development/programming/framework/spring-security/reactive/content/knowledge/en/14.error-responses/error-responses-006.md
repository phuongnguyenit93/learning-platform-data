# Choosing Redirect or JSON by Endpoint Type and Request Content

> **Context:** Spring Security 6.x on Spring WebFlux, Spring Boot 3.3.x, and Java 17+. This lesson focuses on **security error responses**: when a browser should be redirected to the login page, when an API should return JSON with HTTP 401/403, and how to apply policies by **endpoint type (web/API)** plus the **Accept** header. Examples use Spring Boot 3.3.13 for consistent syntax; before deploying to production, choose a currently supported and security-patched Spring version.

## 1. The Problem: Same Authentication Error, Different Client Expectations

One application may simultaneously serve:

- **HTML web pages:** a user opens `GET /web/me` in a browser tab. If not logged in, the usual experience is an HTTP redirect to `/login`.
- **JSON API:** frontend `fetch(...)`, mobile apps, or server-to-server integrations call `GET /api/me`. If not logged in, the client needs HTTP **401** and stable JSON to decide whether to show a login dialog, refresh a token, or ask the user to sign in again.
- **Web page called via AJAX:** path `/web/me` but the request carries `Accept: application/json`; redirecting to an HTML login page would make code expecting JSON receive HTML or cause the browser to follow 302 automatically. **401 JSON** can be chosen instead.
- **Logged-in user lacking permissions:** should not be sent back to the login page like an unauthenticated caller. Should receive **403 Forbidden** in the appropriate representation.

This distinction concerns **response representation**, not changing access permissions. A route requiring `ROLE_ADMIN` still requires that role regardless of whether the client asks for HTML or JSON.

### Decision Model

```text
HTTP request
    |
    v
Authentication (cookie/form, Basic, bearer token, ...)
    |
    v
Authorization (path, method, role, data)
    |
    +--> Allowed -------------------------------------> Controller
    |
    +--> Missing authentication / need to start login
    |            |
    |            +-- Web page + HTML navigation -> 302 /login
    |            |
    |            +-- API or request wanting JSON -> 401 problem+json
    |
    +--> Authenticated but insufficient permissions
                 |
                 +-- Browser HTML navigation     -> 403 HTML
                 |
                 +-- API or request wanting JSON -> 403 problem+json
```

The condition deciding response *content* must never elevate permissions. For requests carrying wrong credentials, the authentication handler can fail **before** the authorization layer; check that branch too, not just `exceptionHandling`.

## 2. Understanding 302, 401, and 403 Correctly

| HTTP status | Meaning in this flow | Common response form | What NOT to do |
|---|---|---|---|
| `302 Found` or appropriate redirect mechanism | Directs unauthenticated HTML client to `/login` | `Location: /login` header, possibly no JSON | Return a login redirect to an API and expect the client to treat it as an auth error |
| `401 Unauthorized` | No valid authentication yet or supplied credentials rejected | JSON with error code; HTTP authentication requires appropriate `WWW-Authenticate` | Turn all cases into 403 just to hide differences |
| `403 Forbidden` | Request blocked despite authentication, or another policy (e.g., CSRF) refused | 403 JSON/HTML | Redirect users with the wrong role back to login, causing a loop |
| `400 Bad Request` | Invalid payload/path/query | Validation error per contract | Call input errors "not authenticated" |
| `404 Not Found` | Endpoint/object does not exist or API intentionally hides resource existence | 404 JSON/HTML | Believe every 404 means Spring Security checked permissions |
| `405 Method Not Allowed` | Handler does not support that HTTP method | Framework response | Expect 405 if security denyAll blocks before the controller |
| `406 Not Acceptable` | Cannot produce a valid representation per handler content negotiation | HTTP 406 | Turn every unfamiliar Accept into a 302 login |
| `429 Too Many Requests` | Rate limit threshold exceeded | JSON/headers about rate limit | Mix with 401/403 when applying login throttling |

**401 does not equal "wrong password".** It also applies when **no** credentials were sent for a protected resource. With HTTP Basic/Bearer, the server should return a protocol-compliant `WWW-Authenticate` challenge; the API example below uses Basic so it proactively returns `WWW-Authenticate: Basic realm="api"`.

**403 is not always just "logged in but missing role".** The CSRF filter can reject POST/DELETE with 403, and other filters/exception handlers may format responses in their own way. Test the CSRF branch directly instead of assuming every 403 error passes through one custom `ServerAccessDeniedHandler`.

## 3. Three Questions Before Choosing a Response

### 3.1 Is This an API or a Web Page?

Classifying by **route contract** is more stable than guessing the client:

- `/api/**`: **always** return a machine-readable response on authentication/authorization errors, even if the client sends `Accept: text/html`.
- `/web/**`: can return HTML/redirect for **navigation**, or JSON when the request explicitly asks for JSON.
- `/login`: the UI flow for form login; does not replace a token-based login endpoint.
- Routes without a clear contract: should have a safe fallback rule, avoiding redirecting webhooks, health checks, or APIs to login unintentionally.

**Path is not proof of identity.** API vs. web classification chooses representation; authentication/authorization must still rely on the `Authentication` provided by Spring Security.

### 3.2 What Does the Client Want to Receive? The Accept Header

`Accept` describes the **response content types** the client accepts. It differs from `Content-Type`, which describes the **request body content** being sent.

```http
GET /web/me HTTP/1.1
Accept: text/html
```

Indicates HTML navigation. Meanwhile:

```http
GET /web/me HTTP/1.1
Accept: application/json
```

Indicates a request wanting JSON. Some HTTP clients send by default:

```http
Accept: */*
```

That is **not** proof the client is a browser navigating a page. In this lesson's policy, `*/*` **does not trigger a redirect**; the fallback is JSON.

Modern browser navigations usually send explicit `text/html` alongside `application/xhtml+xml` and `*/*`. AJAX/fetch may send `*/*` if the developer does not set `Accept`. Do not rely on `User-Agent` or `X-Requested-With` as the sole basis: they may be absent or forged by the client.

### 3.3 Is This a Safe Navigation Operation?

For example, only redirect when a web request uses **GET/HEAD** and declares an **explicit HTML Accept**. POST/PUT/PATCH/DELETE may be rejected earlier by CSRF; redirecting after a non-idempotent operation also confuses clients. The login-success flow has its own redirect managed by the form-login handler and is not governed by this GET/HEAD rule.

**Convention when Accept declares both `text/html` and `application/json`:** the demo intentionally prefers JSON so integration clients do not accidentally receive login HTML. This is a **product convention** of the example, not a general content-negotiation engine evaluating all `q` quality parameters. The code checks `q=0` so rejected media types are not treated as valid.

## 4. Which Interfaces Does WebFlux Security Use?

In Spring Security **reactive**, the two main extension points sit under `ServerHttpSecurity.exceptionHandling(...)`.

### 4.1 ServerAuthenticationEntryPoint

`org.springframework.security.web.server.ServerAuthenticationEntryPoint` accepts a `ServerWebExchange` and an `AuthenticationException`, returning `Mono<Void>`:

```java
Mono<Void> commence(
    ServerWebExchange exchange, AuthenticationException exception);
```

This is a **simplified signature**. The entry point decides behavior when a caller must start authentication: e.g., login redirect, sending status 401, or creating JSON. Built-in implementations include:

- `RedirectServerAuthenticationEntryPoint`: redirects to a configured URL.
- `HttpStatusServerEntryPoint`: sets HTTP status without creating a JSON body.
- `HttpBasicServerAuthenticationEntryPoint`: HTTP Basic challenge.

**Do not confuse** with Servlet's `AuthenticationEntryPoint`. WebFlux uses `ServerAuthenticationEntryPoint` returning a Publisher rather than manipulating a synchronous Servlet response.

### 4.2 ServerAccessDeniedHandler

`org.springframework.security.web.server.authorization.ServerAccessDeniedHandler` handles `AccessDeniedException`, returning `Mono<Void>`:

```java
Mono<Void> handle(
    ServerWebExchange exchange, AccessDeniedException exception);
```

It usually represents **403** when the caller is authenticated but lacks sufficient authority. `HttpStatusServerAccessDeniedHandler` can set the status code; if a JSON/HTML body is needed, write a custom handler.

**Do not place the raw exception message** in the JSON response. Internal details, bean names, role policies, database queries, or token metadata could leak. Return an error code, status, and safe message; keep debug details in protected logs.

### 4.3 ExceptionTranslationWebFilter

Spring Security reactive includes `ExceptionTranslationWebFilter`, connecting security access-denied errors to the entry point or denied handler. It evaluates authentication state and uses a trust resolver when choosing the branch. An `AnonymousAuthenticationToken` may have raw `isAuthenticated()==true`, yet **is not treated as a real logged-in user** when evaluating permissions.

### 4.4 Login Errors and Controller Errors Are Separate Branches

| Where did the error occur? | Component typically coordinating | What to customize for consistent JSON/HTML |
|---|---|---|
| Protected request missing login | `ExceptionTranslationWebFilter` → `ServerAuthenticationEntryPoint` | `exceptionHandling().authenticationEntryPoint(...)` |
| Logged-in user missing permission | `ExceptionTranslationWebFilter` → `ServerAccessDeniedHandler` | `exceptionHandling().accessDeniedHandler(...)` |
| HTTP Basic with wrong credentials | Authentication WebFilter for Basic | Configure `httpBasic(...authenticationEntryPoint(...))`/compatible failure handler |
| Form login POST with wrong password | Authentication WebFilter for form login | `formLogin(...authenticationFailureHandler(...))` |
| Form login POST succeeded | Form login success handler | `formLogin(...authenticationSuccessHandler(...))` |
| Controller throws `ResponseStatusException` | WebFlux error handling mechanism | `@ControllerAdvice`/WebExceptionHandler/app error handling |
| CSRF token missing/invalid | Security CSRF filter | Check CSRF/denied handling path and actual response |
| Disallowed CORS preflight | CORS/security configuration | CORS policy, do not turn into login redirect |

This is why a `@RestControllerAdvice` is **not enough** to alter all Spring Security 401/403 responses: many errors happen inside WebFilters **before** the controller runs.

## 5. Two Configuration Strategies

### 5.1 One SecurityWebFilterChain with an Entry Point Choosing the Response

One approach uses a single chain and inspects route + Accept inside the entry point. This fits if the app shares one authentication policy and different response logic is centralized in one place. However, remember Basic, form-login failure, OAuth2 login, and CSRF have separate handlers that must be tested.

### 5.2 Multiple SecurityWebFilterChains: API First, Web Second

If API and web differ in both authentication scheme and response policy, two chains are clearer:

```text
@Order(0) API chain:
    securityMatcher("/api/**")
    HTTP Basic (demo)
    401/403 -> application/problem+json
    WWW-Authenticate: Basic ...

@Order(1) Web/fallback chain:
    matches remaining requests
    form login + cookie session
    /web/**: 302 login if HTML navigation, 401 JSON otherwise
    403: HTML or problem+json
    /login: generated login page
    other URLs: denyAll()
```

**Warning:** `ServerHttpSecurity.securityMatcher(...)` determines **which chain a request enters**; `authorizeExchange().pathMatchers(...)` only decides permissions **after** the chain is chosen. The API chain at `@Order(0)` handles `/api/**`, and the second chain should not override/block API routes. Conversely, a URL matching no chain risks bypassing security; a fallback is required.

The example below uses the second strategy because it separates API from browser behavior and simplifies testing. All routes illustrate **GET** so the content-negotiation demo does not become a lesson about disabling CSRF. CSRF remains enabled for unsafe operations.

## 6. JSON Error Contract: Problem Details

Instead of ad-hoc HTML login page responses, APIs can standardize on `application/problem+json`, aligning with RFC 9457. A 401 error response:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json;charset=UTF-8
Cache-Control: no-store
WWW-Authenticate: Basic realm="api"

{"type":"about:blank","title":"Unauthorized","status":401,"detail":"Authentication required"}
```

A 403 error response:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json;charset=UTF-8
Cache-Control: no-store

{"type":"about:blank","title":"Forbidden","status":403,"detail":"Access denied"}
```

The `type`, `title`, `status`, and `detail` fields describe the error. With `type: about:blank`, `title` normally matches the HTTP status reason phrase, such as `Unauthorized` or `Forbidden`. Never put rejected usernames, exact missing permissions, passwords, tokens, exception stack traces, or table names into the response.

**HTTP Basic note:** clients need to know how to send credentials, so the API example returns the `Basic realm="api"` challenge. For an OAuth2 resource server using bearer tokens, you must use a compliant `Bearer` challenge (including valid error details when appropriate) instead of copying a Basic header. For APIs using session cookies or custom tokens, design challenges/responses per the real protocol; never invent schemes in `WWW-Authenticate`.

### Status Differs from Representation

Even when a JSON response is desired, the HTTP status must be a **genuine 401/403**; do not return `200 OK` with `{"success":false}` for all errors and break client, caching, and monitoring semantics.

`Cache-Control: no-store` is appropriate to prevent caching sensitive auth error responses. Endpoints should never be arbitrarily shared-cached. For cacheable data, caching policies must account for user, session, and authorization.

## 7. Java 17+ Demo: JSON API and Browser Redirect

The demo uses **Spring Boot 3.3.13** and Spring Security from the BOM. It provides two in-memory users: `alice` has `ROLE_USER`, `admin` has `ROLE_ADMIN`. Web login uses the default login page generated by Spring Security; the API uses HTTP Basic. Passwords are for localhost testing only; production requires TLS and a managed identity source.

### 7.1 Structure

```text
webflux-negotiated-errors/
  settings.gradle
  build.gradle
  src/main/java/demo/errors/ErrorsApplication.java
  src/main/java/demo/errors/SecurityConfiguration.java
  src/main/java/demo/errors/ApiController.java
  src/test/java/demo/errors/ErrorResponseTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-negotiated-errors'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.errors'
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
```

**Do not add `spring-boot-starter-web`**: that is Spring MVC/Servlet. Examples use WebFlux's `ServerHttpSecurity` and `SecurityWebFilterChain`.

### 7.2 Main Application

**src/main/java/demo/errors/ErrorsApplication.java**

```java
package demo.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorsApplication.class, args);
    }
}
```

### 7.3 SecurityConfiguration.java

The file below is the most important part: two chains, two entry-point groups, and a function selecting the representation for web requests.

```java
package demo.errors;

import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
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

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("dev-admin-only"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    @Order(0)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        ServerAuthenticationEntryPoint apiEntry =
            (exchange, failure) -> writeError(
                exchange, HttpStatus.UNAUTHORIZED, false, true);

        ServerAccessDeniedHandler apiDenied =
            (exchange, denied) -> writeError(
                exchange, HttpStatus.FORBIDDEN, false, false);

        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyExchange().denyAll())
            .httpBasic(basic -> basic.authenticationEntryPoint(apiEntry))
            .formLogin(form -> form.disable())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(apiEntry)
                .accessDeniedHandler(apiDenied))
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
        ServerAuthenticationEntryPoint loginRedirect =
            new RedirectServerAuthenticationEntryPoint("/login");

        ServerAuthenticationEntryPoint webEntry = (exchange, error) -> {
            if (wantsHtmlNavigation(exchange)) {
                return loginRedirect.commence(exchange, error);
            }
            return writeError(
                exchange, HttpStatus.UNAUTHORIZED, false, false);
        };

        ServerAccessDeniedHandler webDenied = (exchange, error) ->
            writeError(exchange, HttpStatus.FORBIDDEN,
                wantsHtmlNavigation(exchange), false);

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/login", "/error").permitAll()
                .pathMatchers(HttpMethod.GET, "/web/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/web/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/web/me").authenticated()
                .anyExchange().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(basic -> basic.disable())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(webEntry)
                .accessDeniedHandler(webDenied))
            .csrf(Customizer.withDefaults())
            .build();
    }

    private static boolean wantsHtmlNavigation(
            ServerWebExchange exchange) {

        HttpMethod method = exchange.getRequest().getMethod();
        if (method != HttpMethod.GET && method != HttpMethod.HEAD) {
            return false;
        }

        List<MediaType> accepts =
            exchange.getRequest().getHeaders().getAccept();

        boolean explicitHtml = accepts.stream().anyMatch(type ->
            type.getQualityValue() > 0
                && "text".equalsIgnoreCase(type.getType())
                && "html".equalsIgnoreCase(type.getSubtype()));

        boolean explicitJson = accepts.stream().anyMatch(type -> {
            if (type.getQualityValue() <= 0) {
                return false;
            }
            String subtype = type.getSubtype().toLowerCase(
                java.util.Locale.ROOT);
            return "application".equalsIgnoreCase(type.getType())
                && ("json".equals(subtype)
                    || subtype.endsWith("+json"));
        });

        // JSON wins when the client declares both JSON and HTML.
        // Accept */* alone does not trigger a redirect.
        return explicitHtml && !explicitJson;
    }

    private static Mono<Void> writeError(
            ServerWebExchange exchange,
            HttpStatus status,
            boolean html,
            boolean basicChallenge) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().set(HttpHeaders.CACHE_CONTROL, "no-store");

        if (basicChallenge && status == HttpStatus.UNAUTHORIZED) {
            response.getHeaders().set(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"api\"");
        }

        String body;
        if (html) {
            response.getHeaders().setContentType(
                new MediaType(MediaType.TEXT_HTML, StandardCharsets.UTF_8));
            body = "<!doctype html><html lang=\"en\">"
                + "<meta charset=\"utf-8\">"
                + "<title>Forbidden</title><body>"
                + "<h1>403 Forbidden</h1>"
                + "<p>You do not have permission to access this resource.</p>"
                + "</body></html>";
        } else {
            response.getHeaders().setContentType(
                new MediaType(
                    MediaType.APPLICATION_PROBLEM_JSON,
                    StandardCharsets.UTF_8));

            body = (status == HttpStatus.UNAUTHORIZED)
                ? "{\"type\":\"about:blank\","
                    + "\"title\":\"Unauthorized\","
                    + "\"status\":401,"
                    + "\"detail\":\"Authentication required\"}"
                : "{\"type\":\"about:blank\","
                    + "\"title\":\"Forbidden\","
                    + "\"status\":403,"
                    + "\"detail\":\"Access denied\"}";
        }

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(bytes)));
    }
}
```

**Points to read carefully in the code:**

1. `@Order(0)` puts the API chain first; `securityMatcher("/api/**")` only matches API URLs. `@Order(1)` is the catch-all chain for the remaining requests, including `/login` and `/web/**`.
2. The API only enables HTTP Basic, **not form login**. When unauthenticated/unauthorized, it returns 401 with JSON and `WWW-Authenticate`, even with `Accept: text/html`.
3. Web only enables form login, **not Basic**. Unauthenticated HTML web navigation requests redirect to `/login`. JSON-style web requests receive 401 JSON.
4. `httpBasic(basic -> basic.authenticationEntryPoint(apiEntry))` also adjusts the failed-authentication branch **inside the Basic filter**, not just unauthorized from `authorizeExchange`. This is easy to miss if you only customize `exceptionHandling`.
5. `.exceptionHandling(...authenticationEntryPoint(...).accessDeniedHandler(...))` uses Spring Security 6's lambda DSL, not the legacy `.and()`.
6. When the role is wrong, the `ServerAccessDeniedHandler` branch returns 403; HTML web receives 403 HTML rather than redirecting back to login.
7. `wantsHtmlNavigation` only chooses redirect/HTML for GET/HEAD with **explicit** `Accept: text/html` and without requesting JSON. `Accept: */*` or JSON yields JSON. This is the demo's specific policy, not Spring Security's default heuristic.
8. HTML and JSON bodies are static strings; the code puts no exception text/paths/usernames from the client into responses, preventing injection and internal data leaks.
9. `csrf(Customizer.withDefaults())` stays enabled; the demo only exposes GET. If adding write endpoints using cookies/forms, implement CSRF tokens properly instead of disabling them to fix 403 errors.
10. `MapReactiveUserDetailsService` is an in-memory example; passwords are BCrypt hashed. In real environments, use an appropriate identity store/IdP, TLS, and session/token management policies.
11. There is no third `SecurityWebFilterChain` bean because `webChain` has no `securityMatcher`, creating a **full fallback covering everything** outside the API. Unlisted URLs hit `denyAll()`.

**Why use `@Order` on both beans?** With multiple security chains, Spring Security picks the first chain whose matcher matches. If a catch-all chain ran before the API chain, the API could accidentally receive form login/redirects.

**Why have both `httpBasic(...authenticationEntryPoint(...))` and `exceptionHandling(...authenticationEntryPoint(...))` on the API chain?** The HTTP Basic **wrong credentials** branch may be handled by the authentication filter itself; the **no credentials** branch where authorization demands login uses exception handling. Putting the same policy in both places avoids having one branch return JSON while the other falls back to the default response.

### 7.4 Controller: HTML Pages and JSON API

**src/main/java/demo/errors/ApiController.java**

```java
package demo.errors;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record Identity(String username) {}

    @GetMapping(value = "/api/public",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Identity> apiPublic() {
        return Mono.just(new Identity("public"));
    }

    @GetMapping(value = "/api/me",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Identity> apiMe(Principal principal) {
        return Mono.just(new Identity(principal.getName()));
    }

    @GetMapping(value = "/api/admin",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Identity> apiAdmin(Principal principal) {
        return Mono.just(new Identity(principal.getName()));
    }

    @GetMapping(value = "/web/public",
                produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> webPublic() {
        return Mono.just("<html><body><h1>Public</h1></body></html>");
    }

    @GetMapping(value = "/web/me",
                produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> webMe() {
        return Mono.just("<html><body><h1>Member</h1></body></html>");
    }

    @GetMapping(value = "/web/admin",
                produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> webAdmin() {
        return Mono.just("<html><body><h1>Admin</h1></body></html>");
    }
}
```

**Note:** `produces = ...` only describes the content type of **successful responses produced by the controller**. It **does not** determine 401/403 error responses from Spring Security WebFilters. Hence an unauthenticated API request can receive `application/problem+json` before a handler is selected, even when the client sends `Accept: text/html`; conversely, an **authenticated API request** accepting only text/html may get 406 from the controller because it only produces JSON. Those are two different content-negotiation layers.

In the web controller, HTML uses static strings. If inserting usernames or user data into HTML, use safe HTML escaping/templating; never concatenate arbitrary data directly into HTML responses.

### 7.5 Running with Gradle and curl

From the project directory (JDK 17+ and Gradle compatible with Spring Boot 3.3):

```bash
gradle bootRun
```

If the project has a matching-version wrapper, you can use `./gradlew bootRun`; Windows uses `gradlew.bat bootRun`.

Experiments with the curl CLI:

```bash
# Public API: 200 JSON
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/public

# Protected API, even when Accept is HTML: must be 401 JSON
curl -i -H "Accept: text/html" \
  http://localhost:8080/api/me

# Protected API: curl prompts for password when -u only has username
# Enter dev-alice-only at the prompt
curl -i -u alice -H "Accept: application/json" \
  http://localhost:8080/api/me

# Admin API as Alice: lacking ROLE_ADMIN -> 403 JSON
curl -i -u alice -H "Accept: application/json" \
  http://localhost:8080/api/admin

# Web page: browser-like Accept HTML -> 302 to /login
curl -i -H "Accept: text/html" \
  http://localhost:8080/web/me

# Same web URL but client wants JSON -> 401 JSON
curl -i -H "Accept: application/json" \
  http://localhost:8080/web/me

# Accept */* is not enough to infer navigation
curl -i -H "Accept: */*" \
  http://localhost:8080/web/me

# Default Spring Security login page
curl -i -H "Accept: text/html" \
  http://localhost:8080/login
```

**Do not use `curl -L` when inspecting a 302 redirect**, because `-L` automatically follows to the login page and the final result may be 200 HTML, masking the initial response status.

With PowerShell, you may need `curl.exe` since `curl` is an alias for another command. Never type real passwords into URLs or script logs; demo passwords are local only. A browser actually logging in through the form sends a POST to `/login` with a CSRF token; that is a **separate form-login flow**, not a POST to a Basic-authenticated API.

### 7.6 Result Matrix

| Route and situation | Status | Content type / Location | Meaning |
|---|---|---|---|
| `GET /api/public` anonymous | 200 | `application/json` | Public API |
| `GET /api/me` anonymous, `Accept: text/html` | 401 | `application/problem+json` + Basic challenge | API contract prefers JSON |
| `GET /api/me` valid Basic alice | 200 | `application/json` | API authentication succeeded |
| `GET /api/admin` valid Basic alice | 403 | `application/problem+json` | Authenticated but lacks ADMIN |
| `GET /api/admin` valid Basic admin | 200 | `application/json` | Correct role |
| `GET /web/me` anonymous, `Accept: text/html` | 302 | `Location: /login` | Browser navigation |
| `GET /web/me` anonymous, `Accept: application/json` | 401 | `application/problem+json` | Web endpoint called via AJAX |
| `GET /web/me` anonymous, `Accept: */*` | 401 | `application/problem+json` | Does not assume browser |
| `GET /web/admin` user missing role, `Accept: text/html` | 403 | `text/html` | Does not redirect back to login |
| `GET /web/admin` user missing role, `Accept: application/json` | 403 | `application/problem+json` | JSON access denied |
| `GET /login` not logged in | 200 | HTML login page | Form login chain |
| `POST /login` wrong password | Depends on form-login failure handler (defaults to login?error) | HTML/redirect of form flow | Not the 401 branch of `exceptionHandling` |

The table describes **expected behavior of the demo configuration**; with additional filters, OAuth2/SAML handlers, reverse proxies, or other exception handlers, actual responses may differ. Always test the exact deployed dependencies and chains.

## 8. Automated Testing with WebTestClient

Tests use a **mock** WebFlux application context and apply Spring Security Test. For the API, real HTTP Basic is used to test both valid and invalid credential branches. For web, `mockUser` simulates an authenticated user to focus on verifying **representation on access denied**; it does not test the entire cookie-based login step.

**src/test/java/demo/errors/ErrorResponseTest.java**

```java
package demo.errors;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ErrorResponseTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void apiMissingCredentialIsJsonEvenWithHtmlAccept() {
        client.get().uri("/api/me")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON)
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Basic .*")
            .expectBody()
            .jsonPath("$.status").isEqualTo(401);
    }

    @Test
    void apiBadBasicPasswordIsJson() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.status").isEqualTo(401);
    }

    @Test
    void apiSuccessfulBasicRequestIsJson() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("alice");
    }

    @Test
    void apiInsufficientRoleIsJson403() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.status").isEqualTo(403);
    }

    @Test
    void webNavigationWithoutLoginRedirects() {
        client.get().uri("/web/me")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isFound()
            .expectHeader().valueMatches(
                HttpHeaders.LOCATION, ".*/login");
    }

    @Test
    void webAjaxWithoutLoginGetsJson401() {
        client.get().uri("/web/me")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.status").isEqualTo(401);
    }

    @Test
    void webWildcardAcceptDefaultsToJson401() {
        client.get().uri("/web/me")
            .accept(MediaType.ALL)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON);
    }

    @Test
    void webHtmlAndJsonAcceptChoosesJson() {
        client.get().uri("/web/me")
            .accept(MediaType.TEXT_HTML, MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON);
    }

    @Test
    void webAuthenticatedUserWithoutAdminGetsHtml403() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/web/admin")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_HTML);
    }

    @Test
    void webAuthenticatedUserWithoutAdminGetsJson403() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/web/admin")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.status").isEqualTo(403);
    }

    @Test
    void adminCanReadWebAndApi() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
            .get().uri("/web/admin")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-only"))
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("admin");
    }

    @Test
    void unlistedWebPathIsDenied() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
            .get().uri("/web/unknown")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

The static imports are line-wrapped between package tokens for readability; **Java allows whitespace between qualified-name tokens**. When copying, you can reformat them into **single lines** for convention:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
```

Use the exact **two import statements** above (in place of the wrapped import lines in the sample file) for clarity when building. `mockUser` attaches a SecurityContext to the request at the test layer and does not represent real password/form-login verification; that is why API tests use real Basic credentials.

Run:

```bash
gradle test
```

The project has **12 test methods**. They are expected to PASS when Spring Boot/Spring Security, Java/Gradle, and the classpath match the example. They verify branching logic and JSON/HTML statuses, **not end-to-end form login POST/CSRF/session cookie flows**. You must add browser or integration client tests when implementing real login. Do not treat this description as proof of a build run: the lesson does not run `gradle test` for the reader.

**Especially important:** anonymous tests do not use `mockUser`, so they genuinely enter the missing-identity branch. Role-denied tests use `mockUser` to force the request to carry an `Authentication` without sufficient roles; if every case used mock admin, you could not prove 401 and 403 are separated properly.

## 9. Behaviors **Not** Fully Controlled by exceptionHandling

### 9.1 Form Login Wrong Password

`POST /login` with wrong username/password may be handled by `ServerAuthenticationFailureHandler`, such as redirecting to `/login?error` under the default form config. Do not expect `exceptionHandling().authenticationEntryPoint(...)` to turn this error into 401 JSON automatically; if an SPA frontend sends login requests via JSON/XHR, design a suitable login mechanism (form endpoint + custom failure/success handlers or a token endpoint). Do not open an ad-hoc token endpoint bypassing CSRF/password protection.

### 9.2 Basic Auth Wrong Credentials

HTTP Basic has its authentication mechanism inside `AuthenticationWebFilter`. If a wrong password is supplied, the filter itself may invoke its own entry point/failure handler. The example configured `httpBasic(basic -> basic.authenticationEntryPoint(apiEntry))` to unify the 401 JSON format. When switching to bearer tokens, configure `oauth2ResourceServer(...)` and an OAuth2-compliant entry point rather than reusing a wrong-scheme Basic challenge.

### 9.3 CSRF and CORS

- **CSRF:** if a request is blocked before authorization due to a missing token, the response may be 403 before the custom accessDenied handler formats it as desired. On form/cookie web apps, CSRF protection remains necessary. Test POST with/without CSRF tokens separately.
- **CORS:** browsers may prevent JavaScript from reading responses if preflight or Origin/headers are not accepted. Do not solve this by redirecting every `OPTIONS` to `/login` or `permitAll("/**")`. Configure CORS properly for origins, methods, and credentials.
- **Form actions and cookies:** redirecting to login on a fetch request may be followed by the client, returning HTML that breaks JSON schemas, or cookies may be omitted due to SameSite/CORS. Let API/SPA clients receive 401 JSON and navigate the UI explicitly.

### 9.4 OAuth2/OIDC Redirects Have Their Own Protocol

OAuth2 Login/OIDC redirects to the Identity Provider's authorization endpoint carrying `state`, `nonce`, and a callback. Do not write a blanket entry point sending every OAuth2 login request straight to `/login` if doing so breaks authorization request resolution, saved requests, or callbacks. Configure per the official flow and test both success and failure.

### 9.5 Controller Errors Are Not Authentication Errors

If a controller throws validation 400 or business 409, do not use `ServerAuthenticationEntryPoint` to turn them into 401. Use `@ControllerAdvice`, WebFlux error handlers, or the application's `ErrorWebExceptionHandler` for the corresponding exception types. Spring Security exceptions arising in the filter chain may not reach controller advice.

## 10. Risks in Redirects and Content Negotiation

### 10.1 Open Redirect and Query Parameters

Never build a redirect target from unvalidated client input:

```java
// SECURITY WRONG: client-sent next may point to an external domain.
String next = exchange.getRequest().getQueryParams()
    .getFirst("next");
// response.getHeaders().setLocation(URI.create(next)); // do not do this
```

This snippet is **intentionally unsafe** and must not be used in production. A fixed redirect to `/login` in the demo prevents open redirects. If `returnUrl` must be supported, allow only normalized internal relative paths, reject protocol-relative `//evil.example`, validate host/scheme when required, and review Spring Security's saved-request policy.

### 10.2 URLs and Headers Do Not Identify Users

- `Accept` is not a credential; any client can send `text/html` or `application/json`.
- `User-Agent`, `X-Requested-With`, `Referer` can be spoofed or absent.
- `Content-Type: application/json` does not prove the caller is an API client.
- `X-User-Id` or unverified claims are not a principal.
- `/api/admin` is not permitted merely because the route name contains admin; the Security chain must enforce `ROLE_ADMIN`.

Only use those signals to select **response representation**/CORS policy when appropriate, never to grant permissions.

### 10.3 Avoid Overly Detailed Error Differences

An API should never return to unauthenticated callers something like:

```json
{"error":"user alice exists but password is invalid"}
```

because it enables user enumeration. Return messages that disclose no private information. Internal logs may record error codes, request IDs, routes, and statuses; never log raw `Authorization`, session cookies, tokens, or passwords.

### 10.4 Caching and Proxy Issues

- 401/403 responses should generally include `Cache-Control: no-store`, especially when carrying authentication-related metadata.
- Reverse proxies/CDNs must never mistakenly cache a response for user A and serve it to user B.
- When redirecting, verify `Location` in environments with context paths, TLS termination, and host forwarding to avoid redirecting to HTTP or the wrong host.
- When choosing HTML for browsers, preserve accurate `Content-Type` and escape data; JSON requires valid UTF-8.
- Test real browsers when using `SameSite`, `Secure` cookies, CORS, and CSRF; mock WebTestClient does not simulate all browser behavior.

## 11. Matrix-Based Testing Technique

| Axis | Important test cases | What it proves |
|---|---|---|
| Route type | `/api/**` and `/web/**` | Does not select the wrong chain |
| Auth state | Missing, invalid, valid USER, valid ADMIN | Separates 401/403/200 |
| Accept | `text/html`, `application/json`, `*/*`, both HTML + JSON | Deterministic response rules |
| HTTP method | GET, POST, OPTIONS, HEAD | Navigation, CSRF, CORS are not guessed wrong |
| Login handling | GET /login, POST /login success/fail | Form handler not confused with entry point |
| Content | JSON schema, status, media type, Location | Client gets the right format |
| Challenge | Basic `WWW-Authenticate`, bearer when applicable | Accurate HTTP auth scheme |
| Redirect | Internal URL; never untrusted `next` | No open redirect |
| Cache | `Cache-Control: no-store` | Reduces risk of caching security responses |
| Multiple chains | Match order, catch-all fallback | No URL slips past security |
| Non-security errors | validation 400, business 409, handler 500 | Controller advice handles the right scope |
| CSRF/CORS | Same-origin/cross-origin, unsafe methods | Does not let login redirect pretend to fix CORS |

In real testing, HTTP clients that auto-follow redirects can hide status 302; use WebTestClient or curl without `-L` to inspect the initial response. A `401` with the right code yet an HTML body still violates an API contract; an error JSON with status 200 is also a bug.

## 12. Practice Exercises

1. Run the project, call `GET /web/me` with `Accept: text/html`; explain why 302 and `Location: /login` occur.
2. Call **the same URL** with `Accept: application/json` or `Accept: */*`. Why does the status become 401 JSON instead of a login redirect?
3. Call `GET /api/me` with `Accept: text/html`. Why does the API policy still pick `application/problem+json`?
4. Change the `/web/admin` rule to `ROLE_USER`; write tests confirming Alice enters while another role cannot. Ensure the test uses no fake headers like `X-Role`.
5. Remove `basic.authenticationEntryPoint(apiEntry)` and try wrong Basic API credentials. Compare body/status with the missing-credentials branch to understand different failure handlers. Restore the unified policy afterward.
6. Access `/web/admin` with a mock user missing ADMIN, once accepting HTML and once accepting JSON. Both must be 403 without "forcing re-login".
7. Send `Accept: text/html, application/json` and explain why the demo intentionally prefers JSON; then change the policy to evaluate `q` weights with tests.
8. Extend the app with `POST /web/profile`; write tests for missing/valid CSRF tokens and distinguish CSRF 403 from missing-role 403.
9. Replace the Basic API with a JWT resource server, keeping the JSON error contract and adding the proper Bearer challenge. Test missing, invalid-signature, expired, and insufficient-scope tokens.
10. Try an `/unexpected` URL outside `/api/**`, verifying the fallback chain denies it; never add a catch-all chain permitting every URL.
11. Write a `@ControllerAdvice` for 400 validation and prove it does not alter 401/403 generated before the controller.
12. Design a safe login redirect for the originally requested path without trusting `next=https://...` and check against protocol-relative redirects.
13. Verify in a real browser that when `fetch` receives 401 JSON, the frontend shows an intentional login prompt instead of mis-parsing HTML.

## Summary

- Choose error responses along **two axes**: route contract (`/api/**` vs web page) and requested content via `Accept`. Never use Accept/User-Agent to **grant permissions**.
- `ServerAuthenticationEntryPoint` decides how to initiate login when authentication is required. `ServerAccessDeniedHandler` controls the response when authenticated yet denied. Form-login failure, HTTP Basic failure, CSRF, CORS, and controller exceptions may pass through **other handlers** and must each be tested.
- Browser **GET/HEAD** explicitly requesting HTML can receive **302 /login**; APIs and web AJAX should receive **401 application/problem+json**. Users with sufficient authentication yet missing a role receive **403**, not a login redirect.
- With Basic/Bearer, HTTP 401 needs scheme-specific `WWW-Authenticate`. Never use Basic headers for OAuth2 token APIs.
- In WebFlux, use `ServerHttpSecurity.exceptionHandling(...)`, `SecurityWebFilterChain`, and reactive handlers returning `Mono<Void>`; do not confuse with Servlet `HttpSecurity`/`AuthenticationEntryPoint`.
- Test thoroughly across **route × Accept × authentication × HTTP method**, keep CSRF/CORS, and define an explicit fallback chain.

## Official Documentation

- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Spring Security 6.3 — `ServerHttpSecurity.ExceptionHandlingSpec`: https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security 6.3 — `ServerHttpSecurity.HttpBasicSpec`: https://docs.spring.io/spring-security/site/docs/6.3.0-M3/api/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security — `RedirectServerAuthenticationEntryPoint`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationEntryPoint.html
- Spring Security — `ServerAccessDeniedHandler`, `HttpStatusServerAccessDeniedHandler`: https://docs.spring.io/spring-security/site/docs/6.3.6/api/org/springframework/security/web/server/authorization/HttpStatusServerAccessDeniedHandler.html
- Spring Security — Reactive OAuth2 Login Advanced, customizing login redirect: https://docs.spring.io/spring-security/reference/6.3/reactive/oauth2/login/advanced.html
- Spring Security — Reactive testing WebTestClient: https://docs.spring.io/spring-security/reference/6.3/reactive/test/index.html
- Spring Framework — WebFlux method arguments, Accept/response handling: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/controller/ann-methods/arguments.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
- RFC 9110 — HTTP Semantics, Accept and WWW-Authenticate: https://www.rfc-editor.org/rfc/rfc9110
