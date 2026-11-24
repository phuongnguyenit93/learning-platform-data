# ServerAccessDeniedHandler for Insufficient-Permission Requests

## Learning Objectives

This lesson belongs to the **Error Responses** section in **Spring Security reactive / Spring WebFlux**. After this lesson, you can:

- Explain how `ServerAccessDeniedHandler` handles an **authenticated request lacking sufficient permissions**, and why the status is usually **HTTP 403 Forbidden**.
- Distinguish `AccessDeniedException` from `AuthenticationException`; distinguish `ServerAccessDeniedHandler` from `ServerAuthenticationEntryPoint` used for **HTTP 401 Unauthorized**.
- Identify the roles of `AuthorizationWebFilter` and `ExceptionTranslationWebFilter` in the WebFlux security chain, including errors emitted by `@PreAuthorize`.
- Use `HttpStatusServerAccessDeniedHandler` when only a status code is needed, or implement a custom `ServerAccessDeniedHandler` when the API needs a **unified JSON** response.
- Register the handler using `ServerHttpSecurity.exceptionHandling(exceptions -> exceptions.accessDeniedHandler(...))` and test it with `WebTestClient`.
- Recognize cases like **CSRF 403**, **OAuth2 Bearer insufficient_scope**, and multiple `SecurityWebFilterChain` beans that require careful handling rather than overriding a single global handler.
- Design error messages that do not leak permission structures, resource data, credentials, or sensitive information; keep error codes stable for the frontend.

> **Scope:** Spring Security **reactive**, using `ServerWebExchange` and returning `Mono<Void>`. Do not mistakenly use `AccessDeniedHandler`/`HttpServletRequest`/`HttpSecurity` from **Servlet MVC**; in WebFlux it is `ServerAccessDeniedHandler`, `ServerHttpSecurity`, and `SecurityWebFilterChain`.

## 1. Why Do We Need an "Insufficient Permissions" Response?

An API usually has two separate security questions:

1. **Who are you?** (authentication): Is there a verified principal/Authentication?
2. **Are you allowed to do this?** (authorization): Does the principal have the appropriate authority/role/scope/ownership?

For example, user `reader` logs in with the right password and has `ROLE_READER`, but sends:

~~~http
GET /api/admin/summary HTTP/1.1
Authorization: Basic <credentials-of-reader>
~~~

The server can **successfully authenticate** user `reader` yet reject `hasRole("ADMIN")`. This is an **access denied** situation. Spring Security WebFlux can use `ServerAccessDeniedHandler` to turn that denial into an HTTP response, usually:

~~~http
HTTP/1.1 403 Forbidden
~~~

If **no credentials are sent** or credentials are wrong, an HTTP Basic API usually returns **401 Unauthorized** and a `WWW-Authenticate` header. Do not force both error types into a "wrong password" message, because an authenticated user cannot solve a 403 by retrying their password.

### 1.1. Quick Decision Table

| Situation | Authentication state | Common HTTP | Notable handling component |
|---|---|---|---|
| No credentials sent to `authenticated()` endpoint | Not authenticated | **401** with Basic challenge | `ServerAuthenticationEntryPoint` |
| Wrong Basic username/password sent | Authentication failed | **401** | Basic authentication failure/entry point |
| Valid Basic sent but missing `ROLE_ADMIN` | Authenticated but lacking permission | **403** | `ServerAccessDeniedHandler` |
| User has the required role | Authenticated and allowed | **200** example | Controller/service |
| Authenticated user rejected by `@PreAuthorize` | Authenticated but lacking method permission | **403** in standard HTTP chain | Reactive method security + exception translation |
| POST missing CSRF token | May or may not have Authentication | Usually **403** | `CsrfWebFilter` and CSRF-specific denied handler |
| Valid Bearer token lacking scope | Authenticated but insufficient scope | **403** per RFC 6750 | Bearer-specific denied handler/challenge |
| Non-existent URL when request passes HTTP policy | Depends | **404** | WebFlux handler/router, not proof of access denied |

These are typical cases, not a rule that "every 401/403 has exactly one cause". With custom exception handling, multiple chains, form login, or gateways, responses may differ. Determine the actual mechanism using traces, scrubbed logs, and integration tests.

## 2. What Is ServerAccessDeniedHandler?

Interface in Spring Security reactive:

~~~java
package org.springframework.security.web.server.authorization;

public interface ServerAccessDeniedHandler {
    Mono<Void> handle(
        ServerWebExchange exchange,
        AccessDeniedException denied);
}
~~~

This is an **abbreviated API signature for learning**, not the complete framework source file. Types to note:

- `ServerWebExchange`: the current WebFlux request/response pair, used to set HTTP status, headers, and body.
- `AccessDeniedException`: exception representing an authorization denial decision.
- `Mono<Void>`: publisher representing response handling; Spring subscribes according to the reactive pipeline—do not manually call `subscribe()` and return prematurely.

The handler **does not grant permissions**, **does not verify passwords**, and **does not change roles**. It receives the denial error and decides what the HTTP client will see after authorization fails.

Implementations worth knowing:

| Type | Usage | Behavior |
|---|---|---|
| `HttpStatusServerAccessDeniedHandler` | Want to return a simple HTTP status. | Sets the configured status code, e.g., `HttpStatus.FORBIDDEN`. |
| Custom lambda/bean implementing `ServerAccessDeniedHandler` | API needs JSON error code, content type, cache policy. | Sets status, headers, writes reactive body, avoids leaking sensitive data. |
| `ServerWebExchangeDelegatingServerAccessDeniedHandler` | Want to select a handler by request matcher. | Evaluates matchers in order, uses the first matching handler, with a default fallback handler. |
| `BearerTokenServerAccessDeniedHandler` | OAuth2 Resource Server needs an RFC 6750 compliant response. | May send a Bearer challenge with error `insufficient_scope` when conditions warrant. |

Do not confuse with Servlet's `org.springframework.security.web.access.AccessDeniedHandler`; the Servlet interface has signature `handle(HttpServletRequest,HttpServletResponse,AccessDeniedException)` and returns `void`.

### 2.1. When Only a Status Is Needed

**Configuration snippet** example with a built-in handler:

~~~java
ServerAccessDeniedHandler deniedHandler =
    new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN);

http.exceptionHandling(exceptions ->
    exceptions.accessDeniedHandler(deniedHandler));
~~~

Place inside a Spring configuration class containing the `SecurityWebFilterChain` bean and import the corresponding types. If there is no specific JSON body requirement yet, this approach is simple and avoids manually managing bytes/charset/response commit.

### 2.2. When the Frontend Needs JSON

An API can define a stable contract:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Không có quyền truy cập."
}
~~~

`code` helps the frontend display status/offer support options; `message` is a safe message containing no internal role names, protected resource IDs, account details, stack traces, or raw payloads.

**Do not use raw `denied.getMessage()` as public JSON.** Internal exceptions can contain expression/route/authority names; such details belong in restricted audits, not in responses to unauthorized callers.

## 3. Where Does It Sit in the WebFilter Chain?

Conceptual flow in Spring Security WebFlux:

~~~text
HTTP request
    |
    v
WebFilterChainProxy
    |
    v
First SecurityWebFilterChain matching securityMatcher
    |
    +--> Authentication filters (HTTP Basic / Bearer / form...)
    |       |
    |       +-- invalid credentials
    |               -> authentication failure handling / 401
    |
    +--> ExceptionTranslationWebFilter (wraps downstream)
    |       |
    |       +-- AuthorizationWebFilter
    |                 |
    |                 +-- policy allows -> Controller/Service
    |                 |
    |                 +-- AccessDeniedException
    |                            |
    |                            +-- not authenticated yet?
    |                            |       -> ServerAuthenticationEntryPoint
    |                            |       -> 401/challenge or login redirect
    |                            |
    |                            +-- authenticated but lacking permission?
    |                                    -> ServerAccessDeniedHandler
    |                                    -> 403 (usually)
    |
    +--> Possible AccessDeniedException in method security
            -> exception translation if error propagates through matching chain
~~~

The diagram only describes responsibilities and does not hard-lock the order of every WebFilter; ordering depends on `SecurityWebFiltersOrder` and specific configuration. A call outside the HTTP pipeline (for example, directly testing a reactive service) may emit `AccessDeniedException` as `Mono.error(...)` **with no HTTP response for the handler to process**.

### 3.1. AuthorizationWebFilter

`AuthorizationWebFilter` reads the current security context and evaluates matchers/rules from `authorizeExchange(...)`. For example:

~~~java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated());
~~~

A `/api/admin/summary` request from a user with `ROLE_READER` will be rejected for lacking `ROLE_ADMIN`. Do not think `ServerAccessDeniedHandler` is where `hasRole` is evaluated; permissions are already decided at the authorization layer, and the handler only turns the error into a response.

### 3.2. ExceptionTranslationWebFilter

`ExceptionTranslationWebFilter` handles `AccessDeniedException` instances arising downstream in the WebFlux security pipeline and chooses the appropriate response based on Authentication/context. Core concept:

- **Insufficient authentication:** need to initiate authentication -> `ServerAuthenticationEntryPoint` (usually 401 or login redirect).
- **Authenticated but denied:** `ServerAccessDeniedHandler` (usually 403).

Do not write code assuming every `AccessDeniedException` goes straight to the 403 handler regardless of anonymous/authentication state. That is precisely why the question "401 or 403?" must be asked before customizing responses.

### 3.3. How Does ServerAuthenticationEntryPoint Differ?

Reactive interface for **initiating authentication**:

~~~java
Mono<Void> commence(
    ServerWebExchange exchange,
    AuthenticationException exception);
~~~

It is used when the client must be asked to authenticate; for example, HTTP Basic returns `401` with `WWW-Authenticate: Basic realm="Realm"` per config. Meanwhile:

~~~java
Mono<Void> handle(
    ServerWebExchange exchange,
    AccessDeniedException denied);
~~~

is the denied handler signature. The method name, exception type, and semantics **are not the same**. Attaching only `accessDeniedHandler(...)` will not automatically replace all responses for wrong username/password or anonymous routes. To customize 401, use the appropriate entry point/failure handler and preserve the challenge per the HTTP authentication scheme.

## 4. Configuring in ServerHttpSecurity.exceptionHandling

WebFlux uses the DSL:

~~~java
@Bean
SecurityWebFilterChain springSecurityFilterChain(
    ServerHttpSecurity http,
    ServerAccessDeniedHandler accessDeniedHandler) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .exceptionHandling(exceptions ->
            exceptions.accessDeniedHandler(accessDeniedHandler))
        .build();
}
~~~

This is an **illustrative configuration method**, requiring a `ServerAccessDeniedHandler` bean and imports `@Bean`, `ServerHttpSecurity`, `SecurityWebFilterChain`, `Customizer`; the hands-on section below provides a complete runnable program.

### 4.1. Two Independent Branches in ExceptionHandlingSpec

| Method | Parameter accepted | Responsibility |
|---|---|---|
| `exceptionHandling(ex -> ex.authenticationEntryPoint(entryPoint))` | `ServerAuthenticationEntryPoint` | Chooses response when authentication is needed, e.g., 401 challenge. |
| `exceptionHandling(ex -> ex.accessDeniedHandler(handler))` | `ServerAccessDeniedHandler` | Chooses response for an authenticated user lacking permissions. |

Both can be configured:

~~~java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(customEntryPoint)
    .accessDeniedHandler(customDeniedHandler));
~~~

This is a **non-standalone snippet**; both beans must be declared in the right place. When an API supports multiple auth schemes (Bearer, Basic, form login), avoid using a Basic-style entry point for every request if doing so breaks RFC/auth challenges.

### 4.2. Attaching a Handler per SecurityWebFilterChain

When there are multiple `SecurityWebFilterChain` beans, Spring Security selects the first chain matching the request by `securityMatcher(...)` and `@Order`. Thus `accessDeniedHandler(...)` is attached to **the configured chain**, rather than automatically applying to every chain or every URL in the application.

For example: the `/api/**` chain returns JSON 403, while the browser `/web/**` chain redirects to an error page or returns HTML per UI design. Configure matchers and fallbacks consistently; if a URL sits outside all chains, Spring Security's denied handler **cannot protect** that URL.

## 5. Creating a Proper Reactive JSON ServerAccessDeniedHandler

Short lambda pattern:

~~~java
ServerAccessDeniedHandler jsonDeniedHandler = (exchange, denied) -> {
    ServerHttpResponse response = exchange.getResponse();

    response.setStatusCode(HttpStatus.FORBIDDEN);
    response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
    response.getHeaders().setCacheControl(CacheControl.noStore());

    byte[] body = (
        "{\"code\":\"ACCESS_DENIED\","
        + "\"message\":\"Không có quyền truy cập.\"}")
        .getBytes(StandardCharsets.UTF_8);

    return response.writeWith(
        Mono.just(response.bufferFactory().wrap(body)));
};
~~~

This is a Java snippet inside a Spring class importing `ServerAccessDeniedHandler`, `ServerHttpResponse`, `HttpStatus`, `MediaType`, `CacheControl`, `StandardCharsets`, and `Mono`. The hands-on section uses the same idea as a runnable bean.

**What is right here:**

1. Uses `ServerWebExchange.getResponse()`, not `HttpServletResponse`.
2. Sets `403 Forbidden` before writing the body.
3. Sets `Content-Type: application/json`.
4. Uses UTF-8 to encode Vietnamese in JSON.
5. Sets `Cache-Control: no-store` to reduce the risk of caching sensitive error/resource content.
6. Writes bytes via the response's own `DataBufferFactory`.
7. Returns `Mono<Void>` from `response.writeWith(...)` and lets WebFlux subscribe; **never** call `block()` or `subscribe()` manually.

**What NOT to do:**

~~~java
// WRONG: returns a success response, does not describe access denied.
return Mono.empty(); // when status, headers, or body have not been set

// WRONG: attempts to write the response twice or write after commit.
response.setStatusCode(HttpStatus.FORBIDDEN);
response.setComplete().subscribe();
return response.writeWith(...); // ... is only a placeholder illustrating the error
~~~

The two snippets above **only illustrate mistakes to avoid**, not standalone runnable code. Once a response is committed, changing status/headers usually has no effect and can throw errors; structure filters/handlers so the response is written only once.

### 5.1. Do Not Write the Exception Message to the Client

Do not do:

~~~java
// DO NOT put exception.getMessage() into client JSON.
String unsafe = denied.getMessage();
~~~

An `AccessDeniedException` can reveal policy names, missing roles, method expressions, resource data, or stack traces. If auditing is needed, write the error category/sanitized data to an appropriately access-controlled logging system; never log Basic credentials, bearer tokens, session cookies, PII, or raw sensitive resources.

### 5.2. Pay Attention to JSON Escaping

The example above uses two **server-owned constant** strings, so the JSON literal is valid. If dynamic values need to be placed in the body, **do not concatenate strings** from raw headers/paths/exceptions; use a framework-supported JSON serializer (Jackson `ObjectMapper`) with an explicit error DTO. A `traceId` value can come from a server-issued correlation ID, but must be validated/truncated to avoid reflecting untrusted data.

### 5.3. Should Content-Length Be Added?

It is not mandatory to set Content-Length manually when using `writeWith`; the server can choose streaming/chunked encoding. What matters for the client is status, Content-Type, and a payload with a stable schema. If you do set Content-Length manually, calculate it in **UTF-8 bytes**, not `String.length()`, because Vietnamese has many multi-byte encoded code points.

## 6. Java 17 Hands-on: One JSON Handler for Both URLs and Business Methods

The example runs with **Java 17**, **Spring Boot 3.5.16**, WebFlux, and Spring Security managed by Spring Boot dependency management. Hardcoded demo accounts and `{noop}` are for localhost only, never for real networks.

Objectives:

- `GET /public` is permitted without credentials.
- `GET /api/me` requires authenticated.
- `GET /api/admin/summary` requires `ROLE_ADMIN` **at the HTTP URL rule**.
- `GET /api/internal/report` only requires authenticated at HTTP, but has `@PreAuthorize("hasRole('ADMIN')")` **at the service**.
- Two users: `reader` (only ROLE_READER) and `admin` (ROLE_ADMIN).
- Both rejected paths when `reader` is authenticated return status **403** and JSON `{"code":"ACCESS_DENIED","message":"Không có quyền truy cập."}`.
- Unauthenticated/wrong-credential requests return **401** via the Basic entry point, not faked by the custom 403 handler as "missing role".

### 6.1. Project Structure

~~~text
webflux-access-denied-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/AccessDeniedWebFluxDemo.java
    └── test/java/example/AccessDeniedIntegrationTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-access-denied-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

JDK 17+ and a Gradle/Gradle Wrapper compatible with Spring Boot 3.5 are required. No need to manually pin a Spring Security version different from the Spring Boot BOM for the demo. In real projects, use a supported release receiving corresponding security patches.

### 6.2. Complete Application

`src/main/java/example/AccessDeniedWebFluxDemo.java`:

~~~java
package example;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class AccessDeniedWebFluxDemo {

    public static void main(String[] args) {
        SpringApplication.run(AccessDeniedWebFluxDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo-pass")
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin-pass")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    ServerAccessDeniedHandler jsonDeniedHandler() {
        return (exchange, denied) -> {
            ServerHttpResponse response = exchange.getResponse();
            response.setStatusCode(HttpStatus.FORBIDDEN);
            response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
            response.getHeaders().setCacheControl(CacheControl.noStore());

            // Use only safe constant error content, without leaking exceptions.
            String json = "{\"code\":\"ACCESS_DENIED\","
                + "\"message\":\"Không có quyền truy cập.\"}";

            byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
            return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
        };
    }

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http,
        ServerAccessDeniedHandler jsonDeniedHandler) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .exceptionHandling(exceptions ->
                exceptions.accessDeniedHandler(jsonDeniedHandler))
            .build();
    }

    @Service
    public static class ReportService {

        @PreAuthorize("hasRole('ADMIN')")
        public Mono<Map<String, String>> internalReport() {
            return Mono.just(Map.of("report", "internal-only"));
        }
    }

    @RestController
    static class ApiController {

        private final ReportService reportService;

        ApiController(ReportService reportService) {
            this.reportService = reportService;
        }

        @GetMapping("/public")
        Mono<Map<String, String>> publicRoute() {
            return Mono.just(Map.of("access", "public"));
        }

        @GetMapping("/api/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "username", principal.getName()));
        }

        @GetMapping("/api/admin/summary")
        Mono<Map<String, String>> adminSummary() {
            return Mono.just(Map.of("access", "admin"));
        }

        @GetMapping("/api/internal/report")
        Mono<Map<String, String>> report() {
            return reportService.internalReport();
        }
    }
}
~~~

**Component by component:**

1. `@EnableWebFluxSecurity` enables reactive web security. `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` activates `@PreAuthorize` on the service.
2. Bean `jsonDeniedHandler` is a `ServerAccessDeniedHandler` lambda with signature `(ServerWebExchange, AccessDeniedException) -> Mono<Void>`.
3. `exceptionHandling(...accessDeniedHandler(...))` attaches the handler to access-denied handling in the HTTP security chain.
4. `/api/admin/**` is blocked by `AuthorizationWebFilter` if the user lacks `ROLE_ADMIN`.
5. `/api/internal/report` passes HTTP policy for an authenticated user, but `ReportService.internalReport()` requires ADMIN via method security. The downstream reactive error is handled by the security chain into a 403 response in the demo configuration.
6. `/api/me` returns the principal authenticated by Spring Security, rather than trusting arbitrary client-sent headers.
7. The JSON handler keeps `code`/`message` stable without returning `denied.getMessage()` to the caller.
8. Form login is disabled so unauthenticated tests clearly see Basic 401.
9. The demo **uses GET only**, to avoid mixing POST CSRF 403 errors into the authorization denial exercise.
10. `{noop}` and hardcoded passwords are only for local execution; production must use a proper `PasswordEncoder`, HTTPS, secrets management, and rate limiting.

### 6.3. Running with Gradle and curl

In the `webflux-access-denied-demo` directory:

~~~bash
gradle bootRun
~~~

If the project has a Gradle Wrapper, Linux/macOS uses `./gradlew bootRun`; Windows uses `gradlew.bat bootRun`. Once the app runs on `localhost:8080`, try:

~~~bash
# 1. Anonymous to public route.
curl -i http://localhost:8080/public

# 2. Anonymous to admin route: expect Basic 401.
curl -i http://localhost:8080/api/admin/summary

# 3. Wrong Basic: authentication fails, also 401.
curl -i -u reader:wrong-pass http://localhost:8080/api/admin/summary

# 4. Authenticated reader lacking role at HTTP rule: 403 JSON.
curl -i -u reader:demo-pass http://localhost:8080/api/admin/summary

# 5. Reader denied by @PreAuthorize at service: 403 JSON.
curl -i -u reader:demo-pass http://localhost:8080/api/internal/report

# 6. Admin accesses both URL rule and service rule.
curl -i -u admin:admin-pass http://localhost:8080/api/admin/summary
curl -i -u admin:admin-pass http://localhost:8080/api/internal/report

# 7. Reader can access route requiring only authenticated.
curl -i -u reader:demo-pass http://localhost:8080/api/me
~~~

On PowerShell, use `curl.exe` when `curl` points to another alias. `-i` shows response headers; `-u` creates the HTTP Basic Authorization header. Avoid putting real passwords on the command line/shell history; here there are only fake credentials for localhost.

**Expected results:**

| Request | Status | Meaningful body/header |
|---|---|---|
| `GET /public` anonymous | **200** | `{"access":"public"}` |
| `GET /api/admin/summary` anonymous | **401** | `WWW-Authenticate: Basic ...`; **does not** use the denied handler's 403 JSON |
| `GET /api/admin/summary` wrong Basic | **401** | Authentication failure; not a missing role |
| `GET /api/admin/summary` valid reader | **403** | JSON `code=ACCESS_DENIED` |
| `GET /api/internal/report` valid reader | **403** | Same JSON because service method security denies |
| `GET /api/admin/summary` valid admin | **200** | `{"access":"admin"}` |
| `GET /api/internal/report` valid admin | **200** | `{"report":"internal-only"}` |
| `GET /api/me` valid reader | **200** | `{"username":"reader"}` |

Example **HTTP response** excerpt when reader is denied:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED","message":"Không có quyền truy cập."}
~~~

This output illustrates the observable part, not the entire byte-for-byte response. HTTP version, header ordering, Content-Length/Transfer-Encoding, Date, and other security headers may vary. Clients should parse JSON by fields rather than comparing full response dumps.

### 6.4. Reading the Results by Security Flow

- `curl -u reader:demo-pass` provides valid credentials for the user with `ROLE_READER`. On the admin route, the authorization rule rejects it and `ExceptionTranslationWebFilter` uses the denied handler -> 403 JSON.
- On `/api/internal/report`, the HTTP rule only requires authenticated, so `reader` passes the HTTP filter. Then service `@PreAuthorize` rejects -> reactive access denied goes through exception translation -> 403 JSON.
- `curl` without credentials does not create a valid Authentication; the Basic entry point receives an authentication requirement -> 401 challenge. Never use the denied handler as a login page.
- For admin, both policies allow access, and controller/service return business JSON.

Do not break `@PreAuthorize` by calling a protected service via `new` or self-invocation within the same bean; the demo uses Spring `@Service` and constructor injection into the controller, ensuring calls go through the Spring bean proxy.

## 7. Integration Tests with WebTestClient

To verify the exact HTTP status and JSON body per the API contract, use Spring Boot test and `WebTestClient`. The following tests verify 401, 403, and 200.

File `src/test/java/example/AccessDeniedIntegrationTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AccessDeniedIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousMustAuthenticateInsteadOfReceiving403Json() {
        client.get().uri("/api/admin/summary")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void wrongPasswordIs401() {
        client.get().uri("/api/admin/summary")
            .headers(h -> h.setBasicAuth("reader", "wrong-pass"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validReaderMissingUrlRoleGets403Json() {
        client.get().uri("/api/admin/summary")
            .headers(h -> h.setBasicAuth("reader", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED")
            .jsonPath("$.message").isEqualTo(
                "Không có quyền truy cập.");
    }

    @Test
    void methodSecurityDenialGetsSame403Json() {
        client.get().uri("/api/internal/report")
            .headers(h -> h.setBasicAuth("reader", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
    }

    @Test
    void adminPassesBothAuthorizationLayers() {
        client.get().uri("/api/admin/summary")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.access").isEqualTo("admin");

        client.get().uri("/api/internal/report")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.report").isEqualTo("internal-only");
    }

    @Test
    void readerCanAccessOwnIdentity() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("reader");
    }

    @Test
    void publicRequestDoesNotNeedCredential() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.access").isEqualTo("public");
    }
}
~~~

Run:

~~~bash
gradle test
~~~

If Gradle Wrapper exists: `./gradlew test` or `gradlew.bat test`. All seven tests are expected to pass given the right code/dependencies. No need to assert exact log/status lines byte-for-byte; error codes, statuses, and essential headers are the contract.

**Limitations of the tests:** Only GET is used, so POST CSRF is not tested yet; Bearer token auth is not tested either. Those are separate mechanisms discussed in section 8. The code is a complete learning example, but you must run build/tests in a real environment to verify outcomes rather than treating an expected status as proof of execution.

## 8. CSRF 403 Does Not Necessarily Use exceptionHandling.accessDeniedHandler

An easily made mistake: sending `POST /api/update` without a CSRF token, receiving 403, and concluding that the JSON handler in section 6 is broken because the response is not JSON. In reality, `CsrfWebFilter` has **its own configurable handler**.

In Spring Security WebFlux, `ServerHttpSecurity.CsrfSpec` provides:

~~~java
http.csrf(csrf ->
    csrf.accessDeniedHandler(jsonDeniedHandler));
~~~

This is a **configuration snippet** inside a `SecurityWebFilterChain` bean that already has `jsonDeniedHandler`. It specifies how invalid CSRF tokens are handled. Meanwhile:

~~~java
http.exceptionHandling(exceptions ->
    exceptions.accessDeniedHandler(jsonDeniedHandler));
~~~

is used for access denied from authorization/exception translation. **These are two different configuration points**; do not assume wiring just one place covers every 403.

### 8.1. Should the Same JSON Body Be Used for CSRF?

It can be if the frontend needs a common schema, though internally they should be distinguished:

- `CSRF_TOKEN_INVALID`: missing/wrong token, which may guide the client to refresh the token/session when policy permits.
- `ACCESS_DENIED`: authenticated but lacking permission for the resource.
- `AUTHENTICATION_REQUIRED`: not yet validly authenticated, needs a 401 entry point.

Exposing all three publicly with overly detailed messages can leak session/account state. Keep public error codes minimal, while internal audits distinguish the causes adequately.

### 8.2. Do Not Disable CSRF Just Because JSON Is Missing

If an application uses cookies/sessions where browsers send credentials automatically, disabling CSRF to make POST return the status you want can create a vulnerability. Configure CSRF tokens and handlers properly; test via `WebTestClient` with `csrf()` or real token flows to avoid confusing authorization 403 with CSRF 403.

For stateless Bearer APIs not relying on automatically sent cookies, the CSRF threat model may differ, yet you must evaluate the rationale before disabling CSRF globally.

## 9. OAuth2 Resource Server: Do Not Lose the Bearer Challenge

With an OAuth2 Resource Server, a **valid** access token lacking scopes may need an HTTP response per **RFC 6750**; `BearerTokenServerAccessDeniedHandler` is designed by Spring Security for this scenario.

Protocol meaning example:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

This is an illustrative excerpt; the actual handler may add `realm`, `scope`, or other parameters depending on configuration and appropriate information level. Do not assume all 403 requests must carry this header.

**Risk of replacing with a single JSON handler:** Overriding the Bearer handler carelessly can drop `WWW-Authenticate` or `error="insufficient_scope"` that OAuth2 clients rely on.

### 9.1. Safe Implementation Approaches

1. If the Resource Server does not need a custom JSON body, keep the default Bearer-specific handler for that chain.
2. If a JSON body is needed, consider **delegating to BearerTokenServerAccessDeniedHandler** to set status/headers first, and then writing the body per response-commit rules; design and test carefully so the response is not written twice.
3. If the application has both HTTP Basic and Bearer, separate them with proper `SecurityWebFilterChain`/matchers, or choose handlers per request with `ServerWebExchangeDelegatingServerAccessDeniedHandler`.
4. Test `401` for missing/expired tokens, `403` for valid tokens lacking scope, `WWW-Authenticate` values, and error schemas.
5. Never put access tokens or internal policy details into JSON/`WWW-Authenticate`.

**Do not** turn every 403 into 401 to make the client "log in again"; a valid token lacking permissions usually needs to be distinguished from a missing/expired token.

## 10. Per-Request Customization with ServerWebExchangeDelegatingServerAccessDeniedHandler

An application may want HTML errors for `/web/**` and JSON for `/api/**`, or return errors by API version. Spring Security provides `ServerWebExchangeDelegatingServerAccessDeniedHandler` to choose a delegate using `ServerWebExchangeMatcher`.

Configuration mindset:

~~~text
403 access denied in security chain
   |
   v
ServerWebExchangeDelegatingServerAccessDeniedHandler
   |
   +-- match /api/** -> JSON ServerAccessDeniedHandler
   |
   +-- match /web/** -> browser handler
   |
   +-- no match -> default denied handler
~~~

Matchers are evaluated in order, and the first matching handler is used. There must be an explicit fallback, especially when adding new routes. If routes belong to **two separate security chains**, configuring the handler on each chain can be simpler. Avoid creating overlapping branching layers where it becomes unclear which policy takes effect.

### 10.1. Returning HTML Errors for Browsers

For server-rendered browser UIs, you may want to redirect to an access-denied page or render HTML. Remember a **403** response means something different from a login redirect: the user is logged in but lacks permissions. If redirecting, consider status codes and UX so the client does not think re-authenticating will fix every permission shortage.

Be careful to avoid loops: if the `/access-denied` page itself is protected by the very role the user failed, it triggers access denied again. If a public error page is needed, configure a dedicated authorize rule and controller per policy.

### 10.2. When Using Custom WebExceptionHandler/@ControllerAdvice

Application global exception handling can intercept `AccessDeniedException` depending on pipeline position. Do not catch every exception and convert it into 500/200. For security exceptions, prefer letting Spring Security translation handle them when inside the security chain, unless there is an explicit, well-tested integration requirement. Do not return raw stack traces or principal details in responses.

## 11. Designing an Error Schema for Production

A consistent API error response should consider:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Không có quyền truy cập.",
  "requestId": "opaque-server-generated-id"
}
~~~

This is an **illustrative schema**, not mandatory output from the demo code. Do not copy the literal string `opaque-server-generated-id` as a fixed ID. Principles:

- `code` is stable per the API contract; the frontend does not parse Vietnamese wording to decide behavior.
- `message` is safe and localizable without exposing specific roles/authorities, other users' permissions, or sensitive resource IDs.
- `requestId` must be generated or safely validated by the server/gateway; used for limited audit lookup without embedding personal info in the ID.
- `timestamp` is optional, and clients should not rely on string/timezone formatting unless required; if used, standardize on ISO 8601/UTC.
- `details` may exist, but must not contain `denied.getMessage()` or stack traces for clients.
- `Content-Type` must be accurate; HTTP status must never be replaced by a JSON field while always returning status 200.
- `Cache-Control: no-store` helps limit caching of error contents, especially for sensitive resources.
- CORS headers, if needed, are configured in the CORS mechanism; 403 does not set Access-Control-Allow-Origin by itself.
- Never return multiple body fragments, and never write to the response after it is committed.

### 11.1. Logging and Observability

To debug access denied events, logs/audits should include:

- request ID/correlation ID, timestamp, normalized route/method;
- user ID/subject **per privacy policy** or pseudonymized ID;
- denial source: HTTP authorization, method security, CSRF, Bearer insufficient_scope;
- policy key/authority category in **internal audits**, never leaked in responses;
- selected security chain/matcher when needed, without logging raw Authorization headers.

Rate-limiting and alerting on abnormal spikes in 403s can help detect privilege probing. However, 403 can come from stale frontend permissions or old session states; do not treat every 403 as an attack.

### 11.2. 403 or 404 to Hide Resource Existence?

HTTP RFCs permit servers to return 404 in certain situations to hide forbidden resources, though this is not `ServerAccessDeniedHandler`'s default rule. If policy requires hiding resource existence, design it explicitly in the authorization/data-access layer, ensure no timing/body side-channel leaks, and test per identity/tenant. Do not blindly turn every 403 into 404: that can mislead clients and mask permission-configuration bugs.

## 12. Common Mistakes

**Mistake 1 — Using the 403 handler for wrong logins.** Wrong login is an authentication failure; use an authentication entry point/handler. Access denied for an authenticated user is a different issue.

**Mistake 2 — Treating every 403 as a missing role.** CSRF, token scopes, method policies, and gateways can all produce 403. Distinguish the source.

**Mistake 3 — Returning status 200 with `{"error":"forbidden"}`.** HTTP clients/proxies/monitoring may treat it as success. Return real 403 and a clear schema.

**Mistake 4 — Swallowing the exception and returning `Mono.empty()`.** Without setting status/body, the response may be treated as success. The handler must complete the response with accurate semantics.

**Mistake 5 — Calling `subscribe()` manually and returning Mono.empty.** The response may not yet be written when the framework completes, causing race/committed-response errors. Return the publisher.

**Mistake 6 — Using Servlet `AccessDeniedHandler` on WebFlux.** Wrong API stack. Use `ServerAccessDeniedHandler` and `ServerWebExchange`.

**Mistake 7 — Wiring only `exceptionHandling.accessDeniedHandler(...)` and expecting CSRF 403 to become JSON.** CSRF has its own `csrf.accessDeniedHandler(...)`. Configure the right point.

**Mistake 8 — Writing raw `AccessDeniedException.getMessage()` to the body.** It can expose internal details. Use safe error codes and generic messages.

**Mistake 9 — Hardcoding permissions inside the denied handler.** The handler is not the place to grant roles or decide ownership. Check permissions in AuthorizationManager/method services.

**Mistake 10 — Assuming `permitAll()` guarantees no security denials.** Authentication filters, CSRF, and method security can still reject; permitAll only governs the corresponding HTTP authorization rule.

**Mistake 11 — Writing the response after commit.** If a filter/controller already sent a body, changing status/headers too late can fail. Design clear exception boundaries.

**Mistake 12 — Using a Basic JSON denied handler to replace a Bearer-specific handler.** Can lose `WWW-Authenticate: Bearer`/`insufficient_scope` per RFC 6750. Choose per chain/scheme.

**Mistake 13 — Attaching a handler to a chain that does not match the URL.** Multiple `SecurityWebFilterChain` beans pick the first matching chain by matcher/order; handlers on other chains do not run.

**Mistake 14 — Comparing raw HTTP responses byte-for-byte.** Headers, content length, and JSON field order can vary; test status/content type/error code.

**Mistake 15 — Using ThreadLocal to read the principal in a reactive handler.** Propagation across asynchronous operators is not guaranteed; use `ServerWebExchange` and the Reactor security context rather than Servlet-style `SecurityContextHolder`.

**Mistake 16 — Ignoring other custom error handlers in the app.** A `@ControllerAdvice` or Gateway/WebExceptionHandler may alter responses; test along the real request path.

**Mistake 17 — Disabling CSRF or dropping authentication for the sake of uniform JSON.** Uniformity is a handler/schema concern, not a reason to remove security layers. Keep security policies and configure responses separately.

## 13. Pre-Deployment QA Checklist

1. **Right stack:** Are `ServerHttpSecurity`/`ServerAccessDeniedHandler` used, not Servlet APIs?
2. **Right chain:** Does the URL match the chain with configured `exceptionHandling.accessDeniedHandler(...)`?
3. **Unauthenticated:** Do requests missing credentials receive 401/challenge or login redirect per mechanism, not an arbitrary 403 JSON?
4. **Wrong credentials:** Are authentication failures kept separate from access denied?
5. **Authenticated lacking role:** Real 403 with JSON code per contract?
6. **Sufficient role:** Request allowed, denied handler does not run, business response accurate?
7. **Method security:** If `@PreAuthorize` is used, are service denials converted to the desired response?
8. **CSRF:** Test POST missing/invalid token separately; is `csrf.accessDeniedHandler(...)` needed?
9. **Bearer:** Do tokens with sufficient/insufficient scope or expired tokens emit RFC 6750 `WWW-Authenticate` and error codes?
10. **Error privacy:** No leaked usernames, missing roles, resource secrets, stack traces, tokens, or cookies?
11. **Reactive response:** Handler returns `Mono<Void>`, no `block()`/`subscribe()`, no post-commit writes?
12. **JSON schema:** Correct `Content-Type`, UTF-8, stable fields, no dynamic JSON built by concatenating raw input?
13. **Cache:** Error responses cached per appropriate policy; consider `no-store`?
14. **Frontend:** Does UI distinguish 401 (login required) from 403 (insufficient permissions) without infinite token/password retries?
15. **Multi-chain:** If both HTML web and JSON API exist, are matchers/order and fallbacks clear?
16. **Observability:** Do logs capture sufficient traces/sanitized causes without raw credentials or secrets?
17. **Regression:** Are there HTTP status/body tests for 401, 403 (HTTP + method), 200, and public?
18. **Deployment:** Are TLS, CORS, gateway/proxy, error mapping, and Spring Security version verified in real runtime?

## 14. Self-Assessment with Answers

**1.** A user sends no credentials to `/api/admin/summary`. Is the custom 403 JSON `ServerAccessDeniedHandler` guaranteed to run?

**Answer:** No. When unauthenticated, Spring Security usually starts authentication via `ServerAuthenticationEntryPoint`, e.g., HTTP Basic 401 and challenge.

**2.** User `reader` is authenticated but lacks `ROLE_ADMIN`; which handler is responsible?

**Answer:** After authorization denial in the WebFlux chain, `ServerAccessDeniedHandler` usually produces 403, which can be custom JSON.

**3.** Can `ServerAccessDeniedHandler` grant `ROLE_ADMIN` itself to allow the request?

**Answer:** It should not, and that is not its responsibility. Permissions are decided by authentication and authorization; the handler only builds the error response.

**4.** Why does `POST /update` without a CSRF token return 403 with a body different from the JSON denied handler?

**Answer:** `CsrfWebFilter` has its own handler configured via `csrf.accessDeniedHandler(...)`; `exceptionHandling.accessDeniedHandler(...)` does not always handle CSRF errors.

**5.** If a Bearer resource server receives a valid token lacking scope, what is the risk of replacing the denied handler with a JSON-only one?

**Answer:** It can drop Bearer `WWW-Authenticate`/`insufficient_scope` per RFC 6750; preserve or choose a scheme-specific response.

**6.** Why shouldn't a 403 response contain `denied.getMessage()`?

**Answer:** The message may include policy names, authorities, method names, resources, or internal info. Use a safe error code and log controlled audit details.

**7.** Is calling `jsonDeniedHandler.handle(...).subscribe()` and returning `Mono.empty()` proper reactive code?

**Answer:** No. It detaches response writing from the pipeline; it can return early, drop errors, or cause double commits. Return the Mono from `writeWith`.

**8.** Distinguish `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler`?

**Answer:** Entry point initiates authentication, usually 401/login redirect; denied handler processes an authenticated user lacking permissions, usually 403.

**9.** Can `HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN)` be used instead of a JSON handler?

**Answer:** Yes, if clients do not need a JSON body. It is a concise built-in implementation for setting an HTTP status.

**10.** With multiple `SecurityWebFilterChain` beans, does chain A's handler automatically receive denials from chain B?

**Answer:** Not by default. Only the first matching chain is used for the request; exception handling configured on the selected chain determines the response.

## Official Documentation

- Spring Security 6.5 — `ServerAccessDeniedHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/ServerAccessDeniedHandler.html
- Spring Security 6.5 — `HttpStatusServerAccessDeniedHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/HttpStatusServerAccessDeniedHandler.html
- Spring Security 6.5 — `ServerHttpSecurity.ExceptionHandlingSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security 6.5 — `ServerHttpSecurity.CsrfSpec` (CSRF-specific denied handler): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CsrfSpec.html
- Spring Security — `ExceptionTranslationWebFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html
- Spring Security — `ServerWebExchangeDelegatingServerAccessDeniedHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ServerWebExchangeDelegatingServerAccessDeniedHandler.html
- Spring Security — `BearerTokenServerAccessDeniedHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/server/BearerTokenServerAccessDeniedHandler.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- RFC 6750 — OAuth2 Bearer token usage/errors: https://www.rfc-editor.org/rfc/rfc6750.html
