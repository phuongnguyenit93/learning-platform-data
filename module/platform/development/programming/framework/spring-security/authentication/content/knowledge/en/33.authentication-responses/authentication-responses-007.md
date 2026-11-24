# Equivalent Error Response Components in Spring Security WebFlux

## 1. Lesson Objectives and Scope

In **Spring Security Servlet**, learners frequently encounter `AuthenticationEntryPoint`, `AccessDeniedHandler`, `AuthenticationFailureHandler`, `ExceptionTranslationFilter`, and methods on `HttpSecurity`. When moving to **Spring WebFlux**, names and usage cannot simply swap `HttpServletResponse` for a reactive type: Spring Security provides **`Server...` interfaces**, **`WebFilter`s**, `ServerHttpSecurity` configuration, and workflows returning `Mono<Void>`.

This lesson answers: **which components generate responses for unauthenticated access, authenticated access lacking permissions, or failed logins in WebFlux?** It also demonstrates setting statuses, redirects, safe JSON errors, and testing with `WebTestClient`.

After studying this, you can:

1. Map error response components accurately from Servlet to WebFlux.
2. Distinguish `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler`, and `ServerAuthenticationFailureHandler`; avoid mixing them up across the three scenarios.
3. Understand `ExceptionTranslationWebFilter` and `AuthenticationWebFilter` in the request protection chain.
4. Configure `.exceptionHandling(...)`, `.formLogin(...)`, `.httpBasic(...)`, and Resource Server per **Spring Security 6.5**.
5. Write **non-blocking** JSON-returning handlers via `ServerWebExchange`, and know when not to strip the standard `WWW-Authenticate` header.
6. Build a runnable Java 17+ Spring Boot WebFlux demo and test 401/403/resource protection with `WebTestClient`.
7. Identify boundaries between **security-filter errors**, **controller errors**, infrastructure faults, and ordinary HTTP errors.
8. Avoid leaking usernames, tokens, or exception details, and prevent response differences usable for account enumeration.

**Scope:** Spring Boot 3.x + Spring Security 6.x, Reactive WebFlux applications with `spring-boot-starter-webflux`; 7.x version notes appear later. Servlet examples are included **strictly for API comparison**; never mix both security filter chain types in one application.

## 2. Correspondence Map: Servlet ↔ WebFlux

| Responsibility | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| HTTP Security configuration | `HttpSecurity` | `ServerHttpSecurity` |
| Filter chain configuration object | `SecurityFilterChain` | `SecurityWebFilterChain` |
| HTTP request/response data | `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange` containing `ServerHttpRequest` / `ServerHttpResponse` |
| When unauthenticated and needing to start auth | `AuthenticationEntryPoint` | **`ServerAuthenticationEntryPoint`** |
| When authenticated yet lacking permissions | `AccessDeniedHandler` | **`ServerAccessDeniedHandler`** |
| When a login attempt fails | `AuthenticationFailureHandler` | **`ServerAuthenticationFailureHandler`** |
| After successful login | `AuthenticationSuccessHandler` | `ServerAuthenticationSuccessHandler` |
| Translating security errors into responses | `ExceptionTranslationFilter` | **`ExceptionTranslationWebFilter`** |
| Handling authentication in filters | `UsernamePasswordAuthenticationFilter` / other auth filters | **`AuthenticationWebFilter`** with matching converter/manager |
| Getting contextual principal/auth | `SecurityContextHolder` (typically thread-bound) | `ReactiveSecurityContextHolder` (Reactor Context) |
| URL allow/deny rules | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| HTTP security testing | `MockMvc` + `spring-security-test` | `WebTestClient` + `spring-security-test` |
| Handler return signature | Usually `void`, writing to servlet response | **`Mono<Void>`** representing asynchronous response writing |

**Package rule:** in WebFlux, most security response classes live under `org.springframework.security.web.server...`, not Servlet's `org.springframework.security.web...`. Classes like `HttpStatusServerEntryPoint`, `RedirectServerAuthenticationFailureHandler`, or `HttpStatusServerAccessDeniedHandler` have very similar names to Servlet counterparts yet **do not share parameter types**.

Illustrative WebFlux interface signatures:

```java
// org.springframework.security.web.server.ServerAuthenticationEntryPoint
Mono<Void> commence(ServerWebExchange exchange,
                    AuthenticationException exception);

// org.springframework.security.web.server.authorization.ServerAccessDeniedHandler
Mono<Void> handle(ServerWebExchange exchange,
                  AccessDeniedException exception);

// org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler
Mono<Void> onAuthenticationFailure(WebFilterExchange webFilterExchange,
                                   AuthenticationException exception);
```

These are **illustrative signatures** (omitting interface/import declarations), not a standalone Java class.

Why does `ServerAuthenticationFailureHandler` receive `WebFilterExchange`? It is invoked from an authentication filter; the wrapper carries **`ServerWebExchange` and `WebFilterChain`**. You can call `webFilterExchange.getExchange()` to write the response. Meanwhile, entry points and access-denied handlers operate directly on `ServerWebExchange`.

## 3. Three Scenarios to Distinguish

| Scenario | Context | Primary Component | Common Outcome |
| --- | --- | --- | --- |
| **Unauthenticated** accessing a protected URL | No valid `Authentication` | `ServerAuthenticationEntryPoint` | API: 401/challenge; browser form: redirect to login |
| **Logged in yet lacking authority** | Valid principal, missing required permission | `ServerAccessDeniedHandler` | HTTP **403 Forbidden** |
| **Submitted credentials for login are wrong** | Authentication filter runs, manager throws `AuthenticationException` | `ServerAuthenticationFailureHandler` | Form: redirect `/login?error`; API: 401/challenge or JSON |
| Valid login | Authentication succeeds | `ServerAuthenticationSuccessHandler` | Redirect or continue per configuration |
| Controller encounters business error | Already inside handler/controller | WebFlux exception handling/application layer | 400/404/409/500 per contract |
| Request rejected by CSRF protection | Access denied at security layer | Handler/filter tied to CSRF policy | Usually 403; not a wrong login password |

**401 and 403 are protocol semantics, not class names:**

- **401 Unauthorized** usually means the client **needs to send/authenticate valid credentials**. With HTTP Basic and OAuth2 Bearer, the HTTP challenge in `WWW-Authenticate` carries special meaning.
- **403 Forbidden** usually means the principal is recognized or the request was blocked by a security policy, yet **lacks permission**.
- For **HTML forms**, unauthenticated users typically see a **302/303 redirect** to the login page instead of JSON 401. That can be the right browser-flow behavior.
- If an API receives an **invalid/expired** bearer token, it normally returns 401 per token handling; a valid token lacking required scope normally returns 403 with RFC 6750 metadata.
- A **CSRF** error is a request authorization/security error, not automatically a login failure like wrong username/password.

Never build a single handler returning HTTP 200 and `{success:false}` for every error; it makes clients and monitoring hard to reason about and can blur with successful logins.

## 4. Where Does `ExceptionTranslationWebFilter` Sit?

Conceptual diagram of the WebFlux chain:

```text
HTTP request
    |
    v
WebFilterChainProxy / SecurityWebFilterChain
    |
    +-- AuthenticationWebFilter and authentication filters
    |      |
    |      +-- authenticate succeeds -> store proper security context
    |      |
    |      `-- authenticate fails -> ServerAuthenticationFailureHandler
    |
    +-- ExceptionTranslationWebFilter
    |      |
    |      `-- handles downstream AccessDeniedException
    |             |
    |             +-- insufficient Authentication -> ServerAuthenticationEntryPoint
    |             |
    |             `-- valid Authentication yet lacking permission
    |                               -> ServerAccessDeniedHandler
    |
    +-- AuthorizationWebFilter -> evaluates authorizeExchange(...)
    |
    v
Handler/controller if permitted
```

This is a **responsibility diagram**, not an exhaustive map of every filter or an immutable physical order across all versions.

`ExceptionTranslationWebFilter` has configuration methods:

```text
setAuthenticationEntryPoint(ServerAuthenticationEntryPoint)
setAccessDeniedHandler(ServerAccessDeniedHandler)
```

It converts authorization failures into the right action: **initiating authentication** or **denying access**. However, do not treat it as a `catch` block for **every** `AuthenticationException` in the application. An `AuthenticationWebFilter` can handle credential-submission failures using **its own failure handler**.

Examples:
1. `GET /api/admin` without credentials when policy requires authenticated: entry point.
2. `GET /api/admin` with a `ROLE_USER` user when policy requires `ROLE_ADMIN`: access-denied handler.
3. `POST /login` with wrong password: form login authentication failure handler.
4. `GET /api/data` throws `IllegalStateException` in a service: application error; it does not automatically become 401 just because `exceptionHandling` is configured.

## 5. `ServerAuthenticationEntryPoint`: Starting Authentication When Needed

Interface:

```java
Mono<Void> commence(
    ServerWebExchange exchange, AuthenticationException exception);
```

Common implementations:

| Class | When to Use? |
| --- | --- |
| `HttpStatusServerEntryPoint` | Returns a plain HTTP status, e.g. 401 for JSON API/SPA |
| `RedirectServerAuthenticationEntryPoint` | Redirects to a login page in browser flows |
| `HttpBasicServerAuthenticationEntryPoint` | Returns an HTTP Basic challenge |
| `BearerTokenServerAuthenticationEntryPoint` | Returns an OAuth2 Bearer challenge per RFC 6750 |
| `DelegatingServerAuthenticationEntryPoint` | Selects an entry point based on `ServerWebExchangeMatcher` conditions |

**Packages to distinguish:**

```java
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
```

`HttpStatusServerEntryPoint` alone provides only the **status**; if you want a JSON response body, write a custom handler using `ServerHttpResponse` as in section 9.

### Missing Login vs Wrong Password

Suppose an unauthenticated user opens `/dashboard`: there was no username/password attempt yet. The entry point can redirect to the login page.

If the browser submits a wrong password to `/login`, the **form login filter** already ran and must call the failure handler. Do not convert all such cases into `ServerAuthenticationEntryPoint` and lose endpoint semantics or obscure business causes.

Some failure handlers can **delegate** to an entry point via the `ServerAuthenticationEntryPointFailureHandler` adapter (section 8). That is an **intentional customization**, not evidence that the two interfaces are the same.

## 6. `ServerAccessDeniedHandler`: Authenticated but Lacking Permissions

Interface:

```java
Mono<Void> handle(
    ServerWebExchange exchange, AccessDeniedException exception);
```

Simple implementation:

```java
new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN)
```

Import:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler;
```

It sets only the HTTP status (typically 403). For a JSON body, write a custom handler using `ServerWebExchange`.

In OAuth2 Resource Server, **`BearerTokenServerAccessDeniedHandler`** has special rules: if it determines the request holds a valid OAuth2 authentication yet lacks scope, it can add a challenge with `insufficient_scope` per RFC 6750. Do not replace it with plain JSON 403 and strip information needed by OAuth2 clients.

**Authorization does not mean authentication:** a JWT whose signature was decoded and verified yet lacks `SCOPE_orders:read` usually belongs to the insufficient-permission branch, not password-submission failure. Conversely, a bad JWT signature or expired token must never be treated as an authenticated principal.

## 7. `ServerAuthenticationFailureHandler`: Error During a Login Attempt

Interface:

```java
Mono<Void> onAuthenticationFailure(
    WebFilterExchange webFilterExchange,
    AuthenticationException exception);
```

Common implementations:

- `RedirectServerAuthenticationFailureHandler("/login?error")`: redirects to the credential retry page.
- `ServerAuthenticationEntryPointFailureHandler(entryPoint)`: adapts a failure handler to an entry point.
- A `ServerAuthenticationFailureHandler` lambda returning JSON/status when login APIs do not use redirects.

**Proper configuration placement:**

```java
// Insert into the ServerHttpSecurity DSL of a WebFlux app.
.formLogin(form -> form
    .authenticationFailureHandler(
        new RedirectServerAuthenticationFailureHandler("/login?error")
    )
)
```

Imports:

```java
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
```

With default form login, Spring Security WebFlux usually already redirects to `/login?error` on password errors. You do not need to register a separate handler duplicating default behavior unless you want to adjust UX, unify error contracts, or audit.

**Other protocols have dedicated filters:** `.httpBasic(...)`, `.oauth2Login(...)`, `.oneTimeTokenLogin(...)` in WebFlux have version-specific failure hooks. When configuring, identify **which filter/chain the request actually traverses**. Attaching a custom failure handler to form login does not alter how bearer tokens or API authorization failures respond.

## 8. Turning an Entry Point into a Failure Handler

An API sometimes wants every **failed login attempt** to return the same 401 JSON/status as the entry point. Spring Security provides an adapter:

```java
ServerAuthenticationEntryPoint entryPoint =
    new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

ServerAuthenticationFailureHandler failureHandler =
    new ServerAuthenticationEntryPointFailureHandler(entryPoint);
```

Imports:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
```

The snippet above sits **inside a method**. When `AuthenticationWebFilter` invokes `failureHandler.onAuthenticationFailure(...)`, the adapter invokes `entryPoint.commence(...)` and returns `Mono<Void>`.

This is a case of **reusing behavior** without erasing the distinction among the three interfaces. Never create recursive call cycles (an entry point calling the failure handler back) or continue the filter chain after the response has committed.

## 9. WebFlux Example Returning Error JSON via `Mono<Void>`

When building an API **not requiring HTTP Basic/Bearer challenges**, you may want responses like:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
Cache-Control: no-store

{"error":"UNAUTHENTICATED"}
```

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"error":"ACCESS_DENIED"}
```

In WebFlux, you do not write responses via `response.getWriter().write(...)` like Servlet. You obtain `ServerHttpResponse`, wrap a `DataBuffer`, and **return `Mono<Void>`** for the runtime to execute upon subscription.

File `src/main/java/example/reactive/JsonSecurityErrorHandlers.java`:

```java
package example.reactive;

import java.nio.charset.StandardCharsets;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class JsonSecurityErrorHandlers {

    private JsonSecurityErrorHandlers() {}

    private static Mono<Void> send(
            ServerWebExchange exchange, HttpStatus status, String code) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        response.getHeaders().set("Cache-Control", "no-store");

        // Accepts only server-defined constant error codes.
        byte[] body = ("{\"error\":\"" + code + "\"}")
            .getBytes(StandardCharsets.UTF_8);
        response.getHeaders().setContentLength(body.length);

        return response.writeWith(
            Mono.fromSupplier(() -> response.bufferFactory().wrap(body))
        );
    }

    public static ServerAuthenticationEntryPoint unauthenticated() {
        return (exchange, ex) ->
            send(exchange, HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED");
    }

    public static ServerAccessDeniedHandler denied() {
        return (exchange, ex) ->
            send(exchange, HttpStatus.FORBIDDEN, "ACCESS_DENIED");
    }

    public static ServerAuthenticationFailureHandler invalidCredentials() {
        return (filterExchange, ex) ->
            send(filterExchange.getExchange(),
                 HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS");
    }
}
```

**Conditions for proper use:**
- Class uses **Java 17**, Spring WebFlux/Spring Security reactive, with Reactor provided by the starter.
- Never call `.block()`, `Thread.sleep(...)`, `getWriter()`, or `HttpServletResponse`. Wrapping buffers and returning `Mono` fits the reactive runtime.
- `send` here is strictly for **server-constant** error codes; if putting raw `exception.getMessage()` or user input into JSON, handle escaping/limits and strip sensitive data.
- Status/headers must be set **before** the body is written. Once a response has committed (e.g., an error arises after streaming partial content), you cannot reliably swap status/body; handle errors at the right layer before commit.
- `Content-Length` uses **UTF-8 byte length**, not `String.length()`; for the ASCII strings in the example they match, yet do not generalize that to Vietnamese.
- `Mono.fromSupplier` allocates the `DataBuffer` upon subscription; avoid pre-allocating raw buffers and leaking them on error paths.
- **Do not** drop this JSON handler directly in place of `BearerTokenServerAuthenticationEntryPoint`/`BearerTokenServerAccessDeniedHandler` if clients expect OAuth2 `WWW-Authenticate` headers. Keep the protocol intact, or design a wrapper **preserving standard headers/status**.
- For HTML forms using redirects, JSON 401 may hurt UX; pick handlers per route/media and client contract.

### Attaching Custom JSON Handlers to `ServerHttpSecurity`

Snippet **replacing** `exceptionHandling(...)` inside a WebFlux `SecurityWebFilterChain`:

```java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(
        JsonSecurityErrorHandlers.unauthenticated()
    )
    .accessDeniedHandler(
        JsonSecurityErrorHandlers.denied()
    )
);
```

For form-login failure:

```java
http.formLogin(form -> form
    .authenticationFailureHandler(
        JsonSecurityErrorHandlers.invalidCredentials()
    )
);
```

These are **two illustrative snippets** for an SPA/API web app that may use cookies/sessions; consistent CSRF, session, and login path policies are required. **Do not** copy all snippets at once into section 10's Basic/Bearer demo, as that would alter the headers/challenges and contract the demo tests.

## 10. Complete Demo: WebFlux HTTP Basic with Standard 401 and 403

This example uses Spring Boot **3.x** + Spring Security **6.x** + Java 17+. It genuinely authenticates demo accounts via HTTP Basic and returns exact statuses when unauthenticated or lacking permissions. Section 9's custom JSON is an **alternative** not enabled in this demo.

### 10.1. Gradle Dependencies

In `build.gradle` of a Spring Boot 3.x project with version-managing plugin/BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**Do not add `spring-boot-starter-web`** to the demo if you want a pure WebFlux app on a reactive server. With both MVC and WebFlux on the classpath, Spring Boot normally favors the Servlet/MVC model; adding `SecurityWebFilterChain` while thinking you are running WebFlux can cause config/test errors. In real WebFlux projects, use `@EnableWebFluxSecurity` and `ServerHttpSecurity`.

### 10.2. Security Config

File `src/main/java/example/reactive/ReactiveSecurityConfig.java`:

```java
package example.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/profile").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .exceptionHandling(exceptions -> exceptions
                // Preserve WWW-Authenticate: Basic ... for HTTP Basic clients.
                .authenticationEntryPoint(
                    new HttpBasicServerAuthenticationEntryPoint()
                )
                .accessDeniedHandler(
                    new HttpStatusServerAccessDeniedHandler(
                        HttpStatus.FORBIDDEN
                    )
                )
            )
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-password-for-local-demo"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-password-for-local-demo"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
```

**Explanation:**

- `SecurityWebFilterChain` is WebFlux's request-protection bean, not Servlet's `SecurityFilterChain`.
- `.authorizeExchange` applies rules in order; `/api/admin` needs `ROLE_ADMIN`. User `reader` has only `ROLE_USER`, so requests to admin must return **403** after authentication.
- `.httpBasic(withDefaults())` enables HTTP Basic for the demo; `.formLogin(...::disable)` disables browser form login to avoid unwanted redirects in the API example.
- `.exceptionHandling` picks the **Basic entry point** to keep `WWW-Authenticate`; access-denied handler returns `403`.
- `MapReactiveUserDetailsService` is a **reactive** demo store. Real apps use an appropriate repository, strong password encoder, rate limits, and never store demo passwords in source.
- `BCryptPasswordEncoder` serves Java illustration, which does not mean Basic APIs fit every modern architecture. Real deployments typically prefer OAuth2 Bearer/mTLS/workload identity depending on use case.
- Never send Basic credentials over unencrypted HTTP, URLs, or query strings; HTTPS is mandatory in production.
- `CSRF` remains enabled by default. The demo has only GET endpoints; if adding POST/PUT/DELETE, design CSRF around client/authentication types rather than disabling it system-wide.

### 10.3. Controller and Main Application

File `src/main/java/example/reactive/ReactiveDemoController.java`:

```java
package example.reactive;

import reactor.core.publisher.Mono;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReactiveDemoController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public-ok");
    }

    @GetMapping("/api/profile")
    public Mono<String> profile() {
        return Mono.just("profile-ok");
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

File `src/main/java/example/reactive/ReactiveErrorApplication.java`:

```java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveErrorApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveErrorApplication.class, args);
    }
}
```

Run:

```bash
./gradlew bootRun
```

On a local machine with Java 17+, use HTTP `localhost` **strictly for demo**:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/admin
curl -i -u reader:reader-password-for-local-demo \
    http://localhost:8080/api/admin
curl -i -u admin:admin-password-for-local-demo \
    http://localhost:8080/api/admin
```

**Expected results:**

| Request | Result |
| --- | --- |
| `GET /public`, no auth | HTTP 200, body `public-ok` |
| `GET /api/admin`, no auth | HTTP 401, `WWW-Authenticate` starting with `Basic` |
| `GET /api/admin` with `reader` | HTTP 403, admin controller not executed |
| `GET /api/admin` with `admin` | HTTP 200, body `admin-ok` |
| `GET /api/profile` with `reader` | HTTP 200, body `profile-ok` |
| Login with wrong password | HTTP 401/challenge, no permissions granted |

Table results reflect **expected behavior from the configuration**; no live execution output is claimed here. `curl -u` can expose demo passwords in shell history/process lists; use dummy credentials only in isolated environments. In real environments, use proper secrets management.

## 11. Testing with `WebTestClient`

WebFlux should be tested at the HTTP boundary using `WebTestClient`; do not use `MockMvc` for a reactive `SecurityWebFilterChain`. Below are tests for section 10's demo, **not** a substitute for OAuth2 or SSO integration tests if the real system uses those mechanisms.

File `src/test/java/example/reactive/ReactiveSecurityResponseTest.java`:

```java
package example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ReactiveSecurityResponseTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousCannotAccessAdmin() {
        client.get()
            .uri("/api/admin")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists("WWW-Authenticate");
    }

    @Test
    void readerHasAuthenticationButNotAdminRole() {
        client.get()
            .uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-password-for-local-demo"
            ))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminMayAccessAdmin() {
        client.get()
            .uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-password-for-local-demo"
            ))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void publicEndpointIsAccessibleAnonymously() {
        client.get()
            .uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public-ok");
    }
}
```

Command:

```bash
./gradlew test --tests example.reactive.ReactiveSecurityResponseTest
```

In a project with compatible dependencies, all four tests are expected to pass. They verify:
- 401 **and challenge** when unauthenticated.
- 403 when properly authenticated yet lacking the role.
- 200 when authorized.
- 200 for public URLs.

**If using `SecurityMockServerConfigurers.mockUser(...)` in unit/mock tests**: that creates a **fake** Authentication to test authorization and does not verify password or JWT authentication. The demo above intentionally sends Basic credentials through the test server to exercise the application's authentication pipeline.

### WebTestClient Testing `mockUser` When Omitting Credentials

The snippet below illustrates testing with the Security test configurer:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// Inside a test with WebTestClient client wired with Spring Security.
client.mutateWith(mockUser("reader").roles("USER"))
    .get().uri("/api/admin").exchange()
    .expectStatus().isForbidden();
```

Your setup may need `WebTestClient.bindToApplicationContext(context).apply(springSecurity()).build()` to wire security mock configurers; do not assume every plain WebTestClient supports `mockUser` without adding `spring-security-test`.

## 12. HTML Form Responses: Redirect Instead of JSON

A WebFlux app with a browser login page typically wants:
- `GET /private` when unauthenticated: redirect to `/login`.
- `POST /login` when password is wrong: redirect `/login?error`.
- `POST /login` successful: redirect to an appropriate page.

**Separate** configuration example for browser flows:

```java
http
    .authorizeExchange(exchange -> exchange
        .pathMatchers("/login", "/public").permitAll()
        .anyExchange().authenticated()
    )
    .formLogin(form -> form
        .loginPage("/login")
        .authenticationFailureHandler(
            new RedirectServerAuthenticationFailureHandler(
                "/login?error"
            )
        )
    )
    .exceptionHandling(exceptions -> exceptions
        .authenticationEntryPoint(
            new RedirectServerAuthenticationEntryPoint("/login")
        )
    );
```

Required imports:

```java
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationEntryPoint;
```

**This is a snippet inserted into `ServerHttpSecurity`**, not a second `SecurityWebFilterChain` you can automatically drop next to the Basic demo. When using `.loginPage("/login")`, the app must actually provide a `GET /login` page, form, and CSRF token; Spring Security no longer generates a default login page for custom paths. Unauthenticated users and users submitting wrong passwords may both redirect, yet **the cause and handling hooks differ**.

If replacing redirect handlers with JSON because the frontend is an SPA, proactively manage `fetch`/CSRF/session cookies, while avoiding redirect loops where API requests receive the HTML login page instead of JSON.

## 13. Reactive OAuth2 Resource Server: Keep `WWW-Authenticate`

A common mistake: adding a global JSON entry point across all `/api/**`, wiping out `WWW-Authenticate: Bearer ...` and error metadata expected by OAuth2 clients.

Spring Security WebFlux provides two specialized classes:

```java
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.server.BearerTokenServerAccessDeniedHandler;
```

- **`BearerTokenServerAuthenticationEntryPoint`**: triggers authentication challenge responses per **RFC 6750**, including bearer and token error details when appropriate.
- **`BearerTokenServerAccessDeniedHandler`**: when valid authentication is confirmed yet lacks scope, responds with access denied per RFC, typically carrying `insufficient_scope`.
- With JWTs or opaque tokens, auth failures can occur **right inside the authentication filter**; use default Resource Server wiring or a **spec-respecting** custom handler.

JWT configuration example **replacing the Basic demo**:

```java
http
    .authorizeExchange(exchange -> exchange
        .pathMatchers("/api/public").permitAll()
        .pathMatchers("/api/reports/**")
            .hasAuthority("SCOPE_reports:read")
        .anyExchange().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
        org.springframework.security.config.Customizer.withDefaults()
    ))
    .exceptionHandling(exceptions -> exceptions
        .authenticationEntryPoint(
            new BearerTokenServerAuthenticationEntryPoint()
        )
        .accessDeniedHandler(
            new BearerTokenServerAccessDeniedHandler()
        )
    );
```

A real JWT setup needs `spring-boot-starter-oauth2-resource-server`, `ReactiveJwtDecoder` with proper issuer/JWKs, signature, `aud`, `exp`, `nbf`, and security constraints. This is **only** a security chain snippet; it cannot run end-to-end without a matching Authorization Server/issuer.

Common response differences:

| Bearer Token Status | Typical Handling |
| --- | --- |
| No token sent to protected endpoint | 401 with `WWW-Authenticate: Bearer` |
| Tampered or expired token | 401 `invalid_token` with appropriate error metadata |
| Valid token, missing scope | 403, possibly `insufficient_scope` |
| Valid token, sufficient scope | Request enters handler, bypasses error handlers |
| IdP/decoder infrastructure error | Never label as "wrong user password"; use safe 5xx/availability strategy |

**Do not** interpret `401` in Resource Server the same way as form login's `UsernameNotFoundException`; bearer validation has its own protocol contract. Never leak raw tokens or full exceptions into JSON bodies or `error_description`.

## 14. Multiple SecurityWebFilterChains and Choosing Responses by Route

You might have:
- `/api/**`: JWT, JSON responses, and Bearer challenges.
- `/ui/**`: session cookies, form login, redirects.
- `/actuator/health`: restricted public endpoint or dedicated policy.
- `/internal/**`: internal service/machine authentication.

In WebFlux, chain selection depends on `securityMatcher` and ordering (`@Order`). All security configurers governing error responses also belong to the **selected chain**, not a global configuration arbitrarily applied to every route.

**Diagrammatic** example, not a full project:

```text
@Order(1) API chain:
   securityMatcher("/api/**")
   oauth2ResourceServer(jwt)
   exceptionHandling(Bearer entry point, Bearer denied handler)

@Order(2) UI chain:
   securityMatcher("/ui/**")
   formLogin(...)
   exceptionHandling(redirect entry point, denied page)

Catch-all:
   default deny unless explicitly allowed
```

If `/api/reports` leaks into the UI chain, API clients can receive `302 /login` instead of `401 Bearer`. Conversely, `/ui/profile` falling into the JWT chain can return JSON 401 instead of the login page. Both break UX or create policy bypasses. Test **matcher/chain** routing for every sensitive route.

If an app has both HTML and APIs, prefer **splitting chains by clearly owned routes** rather than guessing from client-supplied `Accept` headers. When using a conditional entry point, never let a client-controlled header change **authentication or authorization** requirements; it may affect only response formatting.

## 15. Do Not Confuse `@RestControllerAdvice`, `ErrorWebExceptionHandler`, and Security Handlers

In WebFlux, errors can arise from several layers:

| Error Layer | Example | Proper Handling Location |
| --- | --- | --- |
| **Security WebFilter** | Unauthenticated, missing role, bad form login | `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler` / `ServerAuthenticationFailureHandler` |
| **Controller/service** | Bad JSON request, validation, business error | `@RestControllerAdvice`, `@ExceptionHandler`, WebFlux app exception mappings |
| **Global WebFlux error** | Error unhandled by controllers | `ErrorWebExceptionHandler` / Spring Boot error infrastructure |
| **Upstream/network** | Gateway timeout, DNS, IdP unavailable | Infrastructure/gateway/proper error path; never rewrite to 401 |
| **CSRF** | POST missing CSRF token in cookie session flow | Security policy; usually 403 or related handler |

`@RestControllerAdvice` usually sees exceptions **only after the request has reached the controller layer**. Security filters block requests before controllers, so exceptions may never reach advice. If you try handling errors with `@ControllerAdvice` while requests still return unexpected 302/401/403, inspect the **security WebFilter chain**.

Similarly, `ErrorWebExceptionHandler` must not be used to reimplement all Spring Security semantics. It does not replace `ServerAuthenticationEntryPoint` or `ServerAuthenticationFailureHandler`.

### System Errors Differ from AuthenticationException

Examples:
- `AuthenticationException`: invalid credentials/tokens or authentication process failure.
- `AccessDeniedException`: authorization policy denial.
- `DataAccessResourceFailureException`: database unavailable.
- `TimeoutException`: IdP/remote server call exceeded deadline.
- `IllegalArgumentException`: invalid request or code.

Never use `onErrorResume(Throwable.class, e -> response401())` across the entire reactive pipeline: a backend outage would be misreported as bad credentials, hiding monitoring alerts and potentially creating logic bypasses. Translate only the right exception types, at the right boundary, preserving error signals for the runtime whenever writing a safe response is impossible.

## 16. Reactive Programming: Why Return `Mono<Void>`?

Reactive handlers must never block threads with synchronous I/O:

```java
// WRONG on the event loop: blocking network/database I/O.
Thread.sleep(500);
mailService.sendBlockingEmail(...);
return Mono.empty();
```

`ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler`, and `ServerAuthenticationFailureHandler` all return `Mono<Void>` representing **completion of writing the response**.

A standard handler may simply set a status:

```java
ServerAuthenticationEntryPoint entryPoint = (exchange, ex) -> {
    exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
    return exchange.getResponse().setComplete();
};
```

This is a **snippet inside a method** (importing `ServerAuthenticationEntryPoint`, `HttpStatus`). When writing a body, return the publisher from `response.writeWith(...)` as in section 9. Never call `.subscribe()` manually and immediately return `Mono.empty()`: the response can commit out of order or be dropped when the request completes.

### Committed Response State

HTTP status and headers normally must be decided **before the first byte of the body**. If permissions are found missing after streaming has started:
- You cannot reliably turn a response that already sent 200 + partial body into a clean 403 response.
- Perform authentication/authorization **before** streaming sensitive data.
- For SSE/streaming, once subscription has started, errors need an event/error protocol and proper stream termination.
- Never push exception classes, tokens, session IDs, or private data into error bodies.

## 17. Authentication and SecurityContext in Reactor

In Servlet, many examples read:

```java
SecurityContextHolder.getContext().getAuthentication();
```

In WebFlux, `SecurityContext` propagates via **Reactor Context**, not simply `ThreadLocal`. If a custom error handler needs the principal, use proper reactive access:

```java
ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .defaultIfEmpty("anonymous");
```

Import:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
```

This is a **snippet producing `Mono<String>`**, not a complete program. Inside an error handler, sometimes no authenticated context exists; never `block()` to read the username and never assume a principal exists in unauthenticated branches.

Operational security: log just enough server-side context (trace ID, endpoint, internal reason code) without writing passwords, JWTs, session cookies, raw OAuth2 errors, or full stack traces into public responses.

## 18. Reducing Information Leakage and Account Enumeration

A login API returning:
- `UNKNOWN_USER` when the username does not exist.
- `BAD_PASSWORD` when the username exists yet the password is wrong.

can become an **account enumeration oracle**. Use `ServerAuthenticationFailureHandler` to normalize the **public response**, such as `INVALID_CREDENTIALS`, for cases that should not be distinguished before proving ownership.

Do not normalize only the JSON body; consider:
- HTTP status, `Location`, `WWW-Authenticate`, `Set-Cookie`.
- Processing time of `ReactiveUserDetailsService`/password hashing.
- Locked/disabled/expired accounts; especially after custom status mapping.
- Whether rate limiting behaves differently depending on username existence.
- MFA enrollment, SSO/home-realm discovery, and recovery endpoints.
- Never turn broken IdP/database errors into "wrong username" when 5xx/monitoring is needed.

Be careful: **uniform login failure responses differ from hiding Bearer protocol errors**. OAuth2 clients rightly expect `invalid_token`/`insufficient_scope` and RFC 6750 challenges. Normalize within each flow's protocol boundaries and threat model, rather than using one universal JSON handler.

### Comparing Response Timing

In a reactive application, one branch running password hashing while another skips it can create a timing side channel. Do not fix that with `Thread.sleep` on the event loop; use standard authentication providers and review `ReactiveUserDetailsService`/encoders. If a blocking data source must be called, prefer non-blocking drivers/reactive APIs; otherwise offload blocking I/O to a bounded scheduler with capacity planning. Never use `.block()` inside security handlers.

## 19. Testing Both HTTP Contracts and Filter Paths

Minimum matrix for a WebFlux application:

| Case | Expected HTTP/Handler |
| --- | --- |
| Anonymous opens protected route in Basic API | `ServerAuthenticationEntryPoint` → 401 `WWW-Authenticate: Basic` |
| Anonymous opens protected route in HTML form | Entry point → login redirect |
| Authenticated user missing role | `ServerAccessDeniedHandler` → 403 |
| User submits wrong password on form | `ServerAuthenticationFailureHandler` → error redirect or JSON 401 |
| JWT bad signature/expired | Resource Server authentication error → 401 Bearer per protocol |
| Valid JWT lacking scope | Resource Server denied → 403, `insufficient_scope` when appropriate |
| Token with sufficient scope | Controller runs normally |
| POST missing CSRF in session/cookie flow | 403/security-denied per policy |
| Controller throws business exception | Application/controller error response, never turns into 401 automatically |
| Server DB/IdP timeout | Infrastructure error handling, never fakes wrong password |
| Custom JSON body | `Content-Type`, `Cache-Control`, status, and body match contract |
| Already-committed response | No extra status/body write or info leak |
| Two security chains | Every request matches the intended chain/handler |
| User has locked/disabled status | Public login response does not disclose account existence |
| Modified Accept header | Does not alter **authentication/authorization requirements** |

### Commonly Misunderstood Tests

- `WebTestClient.mutateWith(mockUser())` injects a mock principal; it **does not** prove password/JWT verifiers ran.
- A `@WebFluxTest` slice spinning up only controllers may not load the full filter chain or authentication backend like production.
- Status 401 is insufficient for Bearer/Basic; check **`WWW-Authenticate`**, realms/scopes when in the contract.
- Mocking a decoder with dummy tokens tests policy/authorization yet **does not** prove signature/issuer/audience verification.
- An HTTP Basic test with a wrong password does not verify the **form login** failure handler if form login is disabled.
- Unit testing `JsonSecurityErrorHandlers.send` does not verify which endpoint uses the handler; integration tests on the real chain are required.

## 20. Common Errors and Remedies

| Symptom | Common Cause | Where to Check |
| --- | --- | --- |
| `AuthenticationEntryPoint` not found in WebFlux | Imported Servlet interface by mistake | Use `ServerAuthenticationEntryPoint` |
| Trying to return `void` from reactive error handler | Copied Servlet code | Return `Mono<Void>` from `setComplete`/`writeWith` |
| API client receives `302 /login` instead of 401 | Form-login/default entry point or wrong chain selected | Check `securityMatcher`, chain order, and entry point |
| HTTP Basic API returns 401 without challenge | Overrode Basic entry point with `HttpStatusServerEntryPoint` | Keep `HttpBasicServerAuthenticationEntryPoint` |
| Invalid JWT returns 401 without `WWW-Authenticate: Bearer` | Overrode Bearer entry point with generic JSON | Use `BearerTokenServerAuthenticationEntryPoint` |
| Valid token lacking scope returns JSON 401 | Conflated authorization denial with authentication failure | Fix `ServerAccessDeniedHandler` and rules |
| Wrong form password still redirects after editing accessDeniedHandler | Error occurs inside `AuthenticationWebFilter` | Configure `formLogin.authenticationFailureHandler` |
| `@RestControllerAdvice` does not catch security errors | Request never reached controller | Configure security handlers, not just controller advice |
| App runs MVC instead of WebFlux | `spring-boot-starter-web` present alongside webflux | Check `WebApplicationType` and dependency tree |
| `mockUser` test passes yet real HTTP Basic fails | Test bypassed password verification | Add integration test with real test credentials |
| `block()` stalls requests / spikes latency | Blocking I/O on Netty event loop | Use reactive publishers and proper schedulers |
| Login message varies by whether username exists | Failure handler echoes raw exception | Normalize public responses, log internal reasons |
| 500 error turned into 401 | Overly broad `onErrorResume` | Map only security exceptions; keep infra errors distinct |
| Handler tries writing 403 after response committed | Authorization occurred too late or bad streaming | Enforce security before streaming |
| Custom entry point behaves unexpectedly | Multiple WebFilter chains/DSLs override it | Audit order/matchers and test via HTTP flows |

## 21. Version Notes

| Version | Key Notes |
| --- | --- |
| **Spring Security 5.x** | WebFlux security already includes `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler`, `ServerAuthenticationFailureHandler` |
| **Spring Security 6.x / Spring Boot 3.x** | Uses Java 17+, `ServerHttpSecurity` lambda DSL, and `SecurityWebFilterChain`; check exact 6.x Javadoc |
| **From Spring Security 6.1** | Many no-arg chained `.exceptionHandling()`/`.httpBasic()` APIs deprecated; prefer `Customizer`/lambdas |
| **Spring Security 7.x / Spring Boot 4.x** | Dedicated reactive APIs remain; review migration/deprecations and authn/authz customizations per minor |
| **Servlet vs Reactive** | Never substitute Servlet `HttpSecurity`, `SecurityFilterChain`, `HttpServletResponse`, or `ExceptionTranslationFilter` for WebFlux |

In particular, merely having a similar name like `HttpStatusEntryPoint` does not mean a class is for WebFlux. `HttpStatusEntryPoint` belongs to Servlet; `HttpStatusServerEntryPoint` belongs to WebFlux.

## 22. Self-Check Questions

**Q1:** In WebFlux, an unauthenticated user opens `/api/private`. Which handler runs?

**Answer:** `ServerAuthenticationEntryPoint`, via the chain's exception translation/entry point. For APIs it usually returns 401/challenge; for browser HTML it may redirect to login.

**Q2:** A logged-in user lacks `ROLE_ADMIN`. Which handler runs?

**Answer:** `ServerAccessDeniedHandler`, typically 403. Do not treat this as a wrong password.

**Q3:** A user submits a wrong password at `POST /login`. Why does `ServerAccessDeniedHandler` not necessarily run?

**Answer:** The failure occurs **right inside the authentication attempt**, usually handled by `AuthenticationWebFilter` invoking `ServerAuthenticationFailureHandler`.

**Q4:** What does `ServerAuthenticationEntryPointFailureHandler` do?

**Answer:** An adapter allowing a `ServerAuthenticationEntryPoint` to be used as a `ServerAuthenticationFailureHandler`.

**Q5:** To send JSON from a reactive handler, should `HttpServletResponse#getWriter()` be used?

**Answer:** No. Use `ServerWebExchange`, `ServerHttpResponse.writeWith(Publisher<DataBuffer>)`, and return `Mono<Void>`.

**Q6:** Why can replacing `BearerTokenServerAuthenticationEntryPoint` with plain JSON 401 be wrong?

**Answer:** Because it can drop the `WWW-Authenticate` header/challenge that OAuth2 clients need to handle `invalid_token`/RFC 6750 compliance.

**Q7:** Why can returning `401` for an `IllegalStateException` in a service be incorrect?

**Answer:** That is not evidence of bad credentials; application/infrastructure errors must be handled at the right layer without disguising outages as authentication failures.

**Q8:** Does `@RestControllerAdvice` replace configuring `.exceptionHandling(...)`?

**Answer:** No. Spring Security errors can be handled inside WebFilters before any controller executes.

## 23. Summary

The three most important interfaces for **authentication/authorization responses in WebFlux** are:

- **`ServerAuthenticationEntryPoint`** — when needing to initiate authentication or handle requests without proper Authentication.
- **`ServerAccessDeniedHandler`** — when a request already has Authentication yet lacks permission.
- **`ServerAuthenticationFailureHandler`** — when an authentication attempt (form/Basic/OAuth2 login or custom filter) fails.

`ExceptionTranslationWebFilter` connects authorization failures to the entry point / denied handler. `AuthenticationWebFilter` has failure/success handlers for the login process. Components operate on `ServerWebExchange`, `Mono<Void>`, and Reactor, rather than Servlet's `HttpServletRequest`/`HttpServletResponse`/`void`.

Configure them via `ServerHttpSecurity.exceptionHandling(...)` and each authentication mechanism's DSL, keep HTTP 401/403/redirect semantics accurate, preserve Basic/Bearer challenges, avoid leaking internal reasons, and test with `WebTestClient` against the right reactive security chain.

## 24. Official References

- Spring Security 6.5 — Reactive Web Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — WebFlux Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/index.html
- Spring Security 6.5 API — `ServerHttpSecurity.ExceptionHandlingSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security 6.5 API — `ServerHttpSecurity.FormLoginSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security 6.5 API — `ServerAuthenticationEntryPoint`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/ServerAuthenticationEntryPoint.html
- Spring Security 6.5 API — `ServerAuthenticationFailureHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationFailureHandler.html
- Spring Security 6.5 API — `ServerAuthenticationEntryPointFailureHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html
- Spring Security 6.5 API — `HttpStatusServerAccessDeniedHandler`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authorization/HttpStatusServerAccessDeniedHandler.html
- Spring Security 6.5 API — `ExceptionTranslationWebFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html
- Spring Security 6.5 — Reactive WebTestClient Testing Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 API — `BearerTokenServerAuthenticationEntryPoint`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAuthenticationEntryPoint.html
- Spring Security 6.5 API — `BearerTokenServerAccessDeniedHandler`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/server/resource/web/access/server/BearerTokenServerAccessDeniedHandler.html
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750.html
