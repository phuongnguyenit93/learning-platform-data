# ExceptionTranslationWebFilter: Translating Security Errors into HTTP Responses

> **Topic:** Spring Security – reactive  
> **Context:** WebFilter Architecture in Spring WebFlux  
> **Focus:** How a Spring Security **access-denial** decision is represented by `AccessDeniedException` and then translated by `ExceptionTranslationWebFilter` into either an authentication challenge branch or an access-denied response. This lesson focuses on **reactive** applications and does not use Servlet configurations.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the responsibility of `ExceptionTranslationWebFilter` inside `SecurityWebFilterChain`, distinguishing it from authentication filters and authorization decision filters.
2. Accurately interpret why the same failed permission check can result in either **401 Unauthorized** or **403 Forbidden**.
3. Distinguish `ServerAuthenticationEntryPoint` from `ServerAccessDeniedHandler`, including the origin of HTTP 401 when a Basic password is wrong.
4. Use `ServerHttpSecurity.exceptionHandling(...)` to customize error responses reactively without blocking threads.
5. Write `WebTestClient` tests covering missing credentials, wrong credentials, logged-in without sufficient permissions, sufficient permissions, and non-security server errors.
6. Diagnose easily confused scenarios: anonymous principals, CSRF failures, multiple security chains, committed responses, and generic exception handlers.

## 2. Why Do We Need a Filter to "Translate" Errors?

The **authorization** layer answers the question: "Is this request permitted to execute?" The **HTTP response** layer must express the outcome in protocol terms: status, headers, body, or redirecting to a login page. The two layers should not be mixed.

For example, endpoint `GET /api/reports` requires role `READER`. When the permission check fails, a downstream component may emit `AccessDeniedException`. If the caller is **unauthenticated**, an API typically needs to respond with **401** so the client knows to provide credentials. If the caller is **authenticated** but lacks `ROLE_READER`, the API typically returns **403** to indicate insufficient permissions.

`ExceptionTranslationWebFilter` bridges **the authorization failure signal** and **how the error is expressed over HTTP**. It is not responsible for matching passwords, decoding JWTs, or deciding whether a user has `ROLE_READER`. Other components handle those tasks.

| Component | Primary Responsibility | What Must NOT Be Assigned to It |
| --- | --- | --- |
| `AuthenticationWebFilter` (e.g., HTTP Basic) | Extracts credentials, triggers authentication, and handles auth success/failure | Does not itself decide all resource authorization rules |
| `SecurityContext` and Reactor `Context` | Carries identity/`Authentication` through the reactive pipeline | Does not automatically permit every request |
| `AuthorizationWebFilter` | Checks access policy and emits a denial signal when permissions are insufficient | Does not itself construct every HTTP error response |
| **`ExceptionTranslationWebFilter`** | Receives an `AccessDeniedException` from downstream, chooses an entry point or access-denied handler | Does not perform authentication or grant permissions |
| `ServerAuthenticationEntryPoint` | Initiates the authentication request flow, e.g., responding 401 + `WWW-Authenticate` | Is not responsible for verifying passwords |
| `ServerAccessDeniedHandler` | Handles denied access cases, typically returning 403 | Is not a password authentication failure handler |
| `WebExceptionHandler` / `@ControllerAdvice` | Handles application errors within that mechanism's scope | Does not replace security policies and security exception handling |

**Exact class names to use:** In WebFlux it is `org.springframework.security.web.server.authorization.ExceptionTranslationWebFilter`. On the Servlet side it is `org.springframework.security.web.access.ExceptionTranslationFilter`. The two classes have similar goals but **different APIs, different mechanics, and different error-catching scopes**.

## 3. Position in the Reactive Filter Chain

A `SecurityWebFilterChain` is a set of Spring Security `WebFilter` instances applied to a request. Simplified model:

```text
                  HTTP REQUEST
                       |
                       v
             WebFlux WebFilter chain
                       |
        [Authentication WebFilter, if present]
                 credentials / token
                       |
         SecurityContext in Reactor Context
                       |
                       v
          ExceptionTranslationWebFilter
                       |
                 chain.filter(exchange)
                       |
                       v
              AuthorizationWebFilter
                       |
                +------+-------+
                |              |
             Allowed      AccessDeniedException
                |              |
         Handler/Service        +--> ExceptionTranslationWebFilter
                |                         |
             Response            +--------+--------+
                                 |                 |
                         Unauthenticated     Authenticated
                                 |                 |
                      AuthenticationEntryPoint  AccessDeniedHandler
                                 |                 |
                            usually 401       usually 403
```

**Note:** This is a diagram of the relevant links, not a complete list of the filter chain. Spring Security also has filters for context, headers, CSRF, CORS, logout, request cache, and more. The standard ordering in `SecurityWebFiltersOrder` places `EXCEPTION_TRANSLATION` before `AUTHORIZATION` so exception handling wraps downstream authorization steps.

When setting up standard Spring Security WebFlux via `ServerHttpSecurity`, the framework configures `ExceptionTranslationWebFilter` automatically. You do **not** need to instantiate `new ExceptionTranslationWebFilter()` yourself or insert another similar filter just to get 401/403. Adding a duplicate filter can cause two error-handling layers, inconsistent responses, and hard-to-trace behavior.

### 3.1. Reactive Mechanism: `onErrorResume`

The core idea of the implementation can be described with **pseudocode**, not an API replacement for Spring Security's source:

```java
// Illustrative pseudocode, not a standalone compilable program:
return chain.filter(exchange)
    .onErrorResume(AccessDeniedException.class, denied -> {
        // Read principal, check whether this is anonymous/unauthenticated
        // or a principal trusted as authenticated.
        // Unauthenticated: authenticationEntryPoint.commence(...)
        // Authenticated: accessDeniedHandler.handle(...)
        return handleAccordingToAuthentication(exchange, denied);
    });
```

Meaning:

- `chain.filter(exchange)` returns a `Mono<Void>` representing the downstream chain.
- If downstream completes normally, the filter does not need to generate an error response.
- When downstream emits `AccessDeniedException` on its reactive error signal, `onErrorResume` can handle it and complete an HTTP response.
- If downstream emits `IllegalStateException` or another application error, the `onErrorResume(AccessDeniedException.class, ...)` branch **does not** automatically turn it into 401/403.
- The filter evaluates authentication status using Spring Security's trust resolver mechanism. Do not replace the whole logic with a naive `authentication.isAuthenticated()` check, because anonymous authentication can carry `isAuthenticated() == true` while still being an anonymous user.

Do not conclude that "every security error is caught directly by `ExceptionTranslationWebFilter`": that mistake is especially easy when comparing with **Servlet `ExceptionTranslationFilter`**. The reactive implementation targets `AccessDeniedException` from downstream; a failed HTTP Basic authentication attempt also has its own handling path inside `AuthenticationWebFilter`.

### 3.2. Related Classes

| Class / Interface Name | Typical Package | Purpose |
| --- | --- | --- |
| `ExceptionTranslationWebFilter` | `org.springframework.security.web.server.authorization` | Translates downstream access-denied errors |
| `AccessDeniedException` | `org.springframework.security.access` | Expresses insufficient permissions |
| `AuthenticationException` | `org.springframework.security.core` | Expresses errors during authentication |
| `ServerAuthenticationEntryPoint` | `org.springframework.security.web.server` | Produces response / request to initiate authentication |
| `ServerAccessDeniedHandler` | `org.springframework.security.web.server.authorization` | Responds when access is denied |
| `AuthenticationWebFilter` | `org.springframework.security.web.server.authentication` | Authenticates reactive requests |
| `AuthorizationWebFilter` | `org.springframework.security.web.server.authorization` | Enforces permissions at the HTTP layer |
| `ServerHttpSecurity` | `org.springframework.security.config.web.server` | Configures `SecurityWebFilterChain` |
| `ReactiveSecurityContextHolder` | `org.springframework.security.core.context` | Accesses security context in Reactor |

## 4. Distinguishing 401, 403, and Application Errors

Do not think "401 = always from `ExceptionTranslationWebFilter`" or "403 = only when missing a role". HTTP status also depends on the authentication mechanism and where the error originates.

| Scenario | Primary Handling Flow | Typical Outcome in a REST API |
| --- | --- | --- |
| No credentials, accessing protected endpoint | Authorization denies → `AccessDeniedException` → exception translation's entry point | **401** and possibly `WWW-Authenticate` |
| Valid credentials, user lacks permission | Authorization denies → `AccessDeniedException` → access-denied handler | **403** |
| HTTP Basic sends wrong password | `AuthenticationWebFilter` detects authentication error and invokes **authentication failure handler** | **401**, may not use the exception-translation entry point's JSON body |
| User has permission | Request passes authorization; handler processes normally | **200**, **201**, etc. per business logic |
| Handler throws `IllegalStateException` | Not an `AccessDeniedException` access error | Typically **500** handled by the application |
| Controller requests non-existent resource | Appropriate business error / `ResponseStatusException` | May be **404**, independent of authentication status |
| POST rejected by CSRF protection | Separate CSRF branch; may use `ServerAccessDeniedHandler` tied to CSRF config | Typically **403**; do not assume wrong role |
| Expired/invalid JWT | Bearer-token authentication/resource-server flow fails | Typically **401** with `WWW-Authenticate: Bearer ...` rules |

### 4.1. Why Can an `AccessDeniedException` Become 401?

Endpoint protection rules do not merely state "insufficient privileges"; in many cases the system does not yet know who the caller is. When encountering an access-denied signal while the principal is not yet considered authenticated, the filter delegates to `ServerAuthenticationEntryPoint` to request authentication. An HTTP Basic entry point typically responds with 401, often with header `WWW-Authenticate: Basic ...`. With form login, the entry point may redirect; an OAuth2 resource server may apply Bearer semantics.

Thus **401/403 is the choice of the handler suited to the security state and authentication mechanism**. They are not two Java exceptions mandated to correspond one-to-one with two statuses.

### 4.2. Do Not Confuse an Anonymous Token with a Logged-In User

Spring Security can create an `AnonymousAuthenticationToken` for an unauthenticated request. That token may return `isAuthenticated() == true` per its object contract, but `AuthenticationTrustResolver` recognizes anonymous as unauthenticated in the sense used to protect resources. For denied requests, the entry point is still typically used. Rely on the `authenticated()` policy and the trust resolver system rather than writing `if (authentication.isAuthenticated()) return 403` yourself.

## 5. Default Configuration and Customizing Handlers

Spring Security WebFlux already includes components for receiving errors. In common configurations:

- The default `ServerAuthenticationEntryPoint` for Basic may use `HttpBasicServerAuthenticationEntryPoint` to generate an authentication challenge.
- A typical `ServerAccessDeniedHandler` is `HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN)`, returning 403.
- `ServerHttpSecurity.exceptionHandling(customizer)` lets you attach an entry point and access-denied handler tailored to a REST API.

**Method contracts:**

```java
// Related interface signatures (illustrative, not a standalone Java file):
Mono<Void> commence(ServerWebExchange exchange,
                     AuthenticationException exception);

Mono<Void> handle(ServerWebExchange exchange,
                  AccessDeniedException denied);
```

`Mono<Void>` means the handler must return a signal indicating the response write is handled asynchronously. Never use `block()` or manual `subscribe()` inside a handler. For an HTTP body, you can use `ServerHttpResponse.writeWith(Publisher<DataBuffer>)`.

Response design rules to keep clear:

1. 401 informs the client of an authentication issue; if using HTTP Basic, preserve a compatible `WWW-Authenticate` header.
2. 403 indicates insufficient permissions, **without** leaking sensitive resource details, internal policies, or stack traces.
3. Response content can follow a uniform schema such as `{"code":"ACCESS_DENIED"}`, with stable, meaningful error codes for clients.
4. Never include verbatim exception messages, passwords, raw tokens, or other user details in the body.
5. If using form login or OAuth2/JWT, the entry point and headers should reflect that mechanism; avoid forcing an HTTP Basic challenge onto every client.

## 6. Runnable Java 17+ Example: A WebFlux API Returning JSON When Blocked

This section is a small Maven project using **Spring Boot 3.5.16**, corresponding to Spring Security 6.x via dependency management. Versions are pinned so the sample is easily reproducible; pick a version actively supported by your real project for production. The demo contains only GET routes and in-memory users to focus on exception translation.

Structure:

```text
reactive-exception-translation-demo/
├── pom.xml
└── src/
    ├── main/java/demo/webfilter/
    │   ├── Application.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/demo/webfilter/
        └── ExceptionTranslationTests.java
```

### 6.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-exception-translation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

With Spring Boot parent, do not insert explicit versions for `spring-security-test`, `spring-boot-starter-security`, or Reactor. `spring-security-test` is used only in tests; WebFlux/Security runtime does not require that artifact.

### 6.2. `src/main/java/demo/webfilter/Application.java`

```java
package demo.webfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 6.3. `src/main/java/demo/webfilter/SecurityConfiguration.java`

```java
package demo.webfilter;

import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/reports").hasRole("READER")
                .anyExchange().authenticated()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint((exchange, error) ->
                    respondJson(exchange, HttpStatus.UNAUTHORIZED, """
                        {"code":"AUTHENTICATION_REQUIRED"}
                        """))
                .accessDeniedHandler((exchange, error) ->
                    respondJson(exchange, HttpStatus.FORBIDDEN, """
                        {"code":"ACCESS_DENIED"}
                        """))
            )
            .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .roles("READER")
            .build();
        UserDetails guest = User.withUsername("guest")
            .password("{noop}guest123")
            .roles("GUEST")
            .build();
        return new MapReactiveUserDetailsService(reader, guest);
    }

    private static Mono<Void> respondJson(
            ServerWebExchange exchange,
            HttpStatus status,
            String json) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        if (status == HttpStatus.UNAUTHORIZED) {
            response.getHeaders().set(
                HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"demo\"");
        }

        byte[] body = json.getBytes(StandardCharsets.UTF_8);
        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(body)));
    }
}
```

Read along the execution line:

- `authorizeExchange(...)` defines **when to deny access**; `ExceptionTranslationWebFilter` does not create the policy itself.
- `httpBasic(withDefaults())` sets up the HTTP Basic authentication path. `formLogin(...disable())` avoids returning HTML redirects in this API demo.
- `exceptionHandling(...)` configures both error-handling branches for the translation filter. You do **not** need to declare a separate `@Bean ExceptionTranslationWebFilter`.
- `authenticationEntryPoint(...)` returns JSON with code `AUTHENTICATION_REQUIRED` and HTTP 401 when a request lacks valid authentication to pass authorization.
- `accessDeniedHandler(...)` returns JSON `ACCESS_DENIED` and HTTP 403 when the principal is authenticated but lacks sufficient permissions.
- `WWW-Authenticate: Basic realm="demo"` is the challenge suited to the Basic scheme in use. If switching to bearer tokens, do not keep the Basic header.
- `respondJson(...)` writes UTF-8 via `Mono` without `block()`/`subscribe()`. The Java 17 text block contains a JSON object and a trailing newline; that is still valid JSON.
- `{noop}` and passwords in source are **solely for local exercises**. Production must use strong password hashes, an appropriate user store, and HTTPS.

**Crucial scope note:** handlers in `exceptionHandling` define the translation branches for `AccessDeniedException`. When a user sends a **wrong Basic password**, the error may be handled earlier by `AuthenticationWebFilter` and `ServerAuthenticationFailureHandler`. Therefore, do not require the JSON body for a wrong-password case to match the entry point's JSON above; the test below asserts only status 401.

### 6.4. `src/main/java/demo/webfilter/DemoController.java`

```java
package demo.webfilter;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicData() {
        return Mono.just("public OK");
    }

    @GetMapping("/reports")
    public Mono<String> reports() {
        return Mono.just("reports OK");
    }

    @GetMapping("/failure")
    public Mono<String> unexpectedFailure() {
        return Mono.error(new IllegalStateException("unexpected failure"));
    }
}
```

`/api/failure` intentionally emits a **non-security application error** to prove exception translation is not a blanket converter turning every exception into 403. Using `Mono.error(...)` sends the error through the reactive error signal. This endpoint requires authentication via `anyExchange().authenticated()`, yet even with a valid user the controller still returns a server error.

## 7. Testing the Proper Role of ExceptionTranslationWebFilter

The tests use `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` to configure Spring Security test support without opening a TCP port. Testing with real Basic users and testing with mocked principals serve different purposes.

### 7.1. `src/test/java/demo/webfilter/ExceptionTranslationTests.java`

```java
package demo.webfilter;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ExceptionTranslationTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicRouteDoesNotNeedAuthentication() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void unauthenticatedRequestStartsAuthentication() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE)
            .expectBody()
            .jsonPath("$.code").isEqualTo("AUTHENTICATION_REQUIRED");
    }

    @Test
    void authenticatedUserWithoutRoleGetsForbidden() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("guest", "guest123"))
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
    }

    @Test
    void readerWithCorrectRolePassesAuthorization() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports OK");
    }

    @Test
    void invalidBasicPasswordFailsAuthentication() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockedGuestIsDeniedByAuthorization() {
        client.mutateWith(mockUser("someone").roles("GUEST"))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
    }

    @Test
    void unrelatedApplicationErrorRemainsServerError() {
        client.get().uri("/api/failure")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().is5xxServerError();
    }
}
```

**Note on `import static` statements:** Java permits line breaks after `server` in an import as shown because the `.` token is part of the import path; if you prefer single-line IDE style, you can write:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
```

Both target the right API in `spring-security-test`; do not use Servlet's `org.springframework.security.test.web.servlet...`.

### 7.2. Test Matrix

| Context | Mechanism Proven | Status | JSON Body to Assert? |
| --- | --- | --- | --- |
| `/api/public` without credentials | `permitAll()` rule | 200 | No; body is `public OK` |
| `/api/reports` without credentials | Access denied → entry point | **401** | `AUTHENTICATION_REQUIRED` |
| `/api/reports`, Basic guest valid password | Access denied → denied handler | **403** | `ACCESS_DENIED` |
| `/api/reports`, Basic reader valid password | Authorization permits | 200 | No; body is `reports OK` |
| `/api/reports`, Basic reader wrong password | Authentication failure path | **401** | Do not enforce exception translation's body |
| `/api/reports`, mocked GUEST | Rule evaluation with fake principal | **403** | `ACCESS_DENIED` |
| `/api/failure`, valid Basic reader | Application error other than `AccessDeniedException` | **5xx** (usually 500) | Do not enforce exception translation's body |

With `mockUser(...)`, Spring Security Test constructs an authenticated principal for that request. That test verifies **authorization**, not that real passwords were verified. Only the Basic tests using `MapReactiveUserDetailsService` also exercise the sample authentication mechanism.

### 7.3. Running Tests and Starting the Application

In the project directory containing `pom.xml`:

```bash
mvn clean test
mvn spring-boot:run
```

With JDK 17+ and compatible Maven/dependencies, Surefire is expected to report **7 tests, 0 failures, 0 errors**. Test names and timings may vary by environment. This guide states the expected outcome from the code; do not treat it as proof that tests were executed on every machine.

In another terminal:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/reports
curl -i -u guest:guest123 http://localhost:8080/api/reports
curl -i -u reader:reader123 http://localhost:8080/api/reports
curl -i -u reader:wrong http://localhost:8080/api/reports
curl -i -u reader:reader123 http://localhost:8080/api/failure
```

On Windows PowerShell, select `curl.exe` if `curl` is aliased to another cmdlet.

**Sample response for a request without credentials** (HTTP header ordering is not fixed):

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Basic realm="demo"

{"code":"AUTHENTICATION_REQUIRED"}
```

**Sample response for Basic guest with valid password but lacking role**:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"code":"ACCESS_DENIED"}
```

**Sample response for Basic reader with valid permissions**:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

reports OK
```

The status codes and JSON codes above follow the sample configuration; versions/transports may vary header representations. Application 500 errors and wrong Basic passwords do not produce a fixed JSON body from `respondJson` in the demo.

## 8. Deep Dive into Three Easily Confused Paths

### 8.1. Request Supplies No Credentials

1. Client calls `GET /api/reports` without `Authorization`.
2. HTTP Basic authentication establishes no identity. The request's security context may contain an anonymous principal.
3. `AuthorizationWebFilter` evaluates `hasRole("READER")` and denies with `AccessDeniedException`.
4. `ExceptionTranslationWebFilter` catches the downstream error signal.
5. The filter uses the trust resolver to determine the caller is not yet authenticated in security terms.
6. `ServerAuthenticationEntryPoint` is invoked; the example configuration returns 401 + `WWW-Authenticate: Basic` + JSON `AUTHENTICATION_REQUIRED`.

**Key takeaway:** this 401 comes from requiring **authentication to proceed** after being denied at authorization.

### 8.2. Request Authenticates Successfully Yet Lacks Permissions

1. Client calls the endpoint with valid Basic credentials for `guest`.
2. `AuthenticationWebFilter` authenticates the user and creates an `Authentication` with `ROLE_GUEST`.
3. `AuthorizationWebFilter` requires `ROLE_READER`, so it emits `AccessDeniedException`.
4. The translation filter sees a principal trusted as authenticated.
5. `ServerAccessDeniedHandler` returns 403 + `ACCESS_DENIED`.

**Key takeaway:** do not use the authentication entry point to "re-login" someone who already proved identity but lacks permissions; the fix is granting the right role or adjusting policy based on real requirements.

### 8.3. Request Carries a Wrong Basic Password

1. Client sends Basic `reader:wrong`.
2. `AuthenticationWebFilter` attempts authentication and receives an authentication error.
3. `ServerAuthenticationFailureHandler` handles the authentication filter's error. With default Basic, the outcome is typically 401 and an authentication challenge.
4. Because the flow fails right inside the authentication filter, **you cannot assume by default** that `ExceptionTranslationWebFilter`'s JSON will be invoked.

**Key takeaway:** customizing `exceptionHandling(...)` **does not guarantee every authentication failure** across the entire system shares the same JSON. To unify responses for wrong Basic passwords, you must also design failure handling on the Basic mechanism (or configure the corresponding entry point per version) and test it separately.

## 9. Scaling to Production Applications

### 9.1. When the API Uses Bearer/JWT

For a resource server using OAuth2 JWT, requests typically carry `Authorization: Bearer <access-token>`. The `oauth2ResourceServer(...)` configuration has its own authentication entry point and access-denied handler, which can generate `WWW-Authenticate: Bearer ...` per HTTP Bearer token rules. In that case:

- **Do not** keep `Basic realm="demo"` from the example.
- Distinguish missing/invalid/expired tokens (authentication) from valid tokens lacking scopes/authorities (authorization).
- Check your version and resource-server setup; a `hasAuthority("SCOPE_report.read")` rule differs from `hasRole("READER")`.
- When customizing JSON, preserve standard-compliant headers for the chosen authentication scheme; test status/headers/body together rather than only the body.

### 9.2. When the Application Uses Form Login / Sessions

The authentication entry point can redirect to the login page (typically 302), rather than forcing every unauthenticated request to return 401. With browser-based sessions, CSRF protection and post-login redirects must be designed consistently. Do not force REST Basic logic onto every HTML request.

### 9.3. When Multiple Security Chains Are Configured

An application may have separate `SecurityWebFilterChain` beans for `/api/**` and `/admin/**`. Spring Security selects the matching security chain per request by order and matcher. Each chain can have a different authentication entry point/denied handler. If JSON 401 appears on one endpoint while another redirects, check **which chain matched** before concluding a filter is malfunctioning.

### 9.4. Method Security and Object-Level Authorization

Reactive method security (e.g., `@PreAuthorize` with `@EnableReactiveMethodSecurity`) can emit `AccessDeniedException` on insufficient permissions. If the error travels through the downstream reactive pipeline wrapped by the translation filter, the corresponding handler can turn it into an HTTP response. However, do not assume errors outside the pipeline or every internal service call goes through the WebFilter.

Specifically, `hasRole("READER")` at the URL layer does not prove the user may read **report #42** or another tenant's report. Ownership, tenant, and resource-state checks belong in the service/repository layer. You may return 403 or 404 per policy, but never leak data before checking.

### 9.5. When the Response Is Already Committed

If a handler has already written headers/body or started streaming data and only then emits a security error, the framework can no longer switch status/body to the desired 401/403 JSON response. For example, emitting a long `Flux` and checking permissions only after the first element is too late. **Authenticate and authorize before emitting sensitive data.** Do not treat exception translation as a mechanism to recall data already sent to the client.

### 9.6. CORS, CSRF, and Generic Exception Handlers

- **CORS:** an `OPTIONS` preflight request does not carry credentials like an actual GET/POST; configure CORS properly for the API and policy. A 401 on preflight is not necessarily due to a missing role.
- **CSRF:** CSRF failures on POST/PUT/DELETE can be handled in the CSRF filter with its own handler. A 403 caused by CSRF is not fixed by granting `ROLE_ADMIN`. Inspect your auth mechanism (cookie/session vs. bearer) before deciding on CSRF policy.
- **Global error handlers:** `@RestControllerAdvice`, `WebExceptionHandler`, or Boot WebFlux error handling are not replacements for all Spring Security responses. Security filters can return responses before the controller ever runs.

## 10. Safe Debugging and Testing

When actual results differ from expectations, verify step by step:

1. **Which endpoint, method, and security chain?** Is the URL pattern right? Does a broad rule precede a specific rule?
2. **Did the failure happen during authentication or authorization?** Missing credentials, wrong credentials, and authenticated lacking authority are three distinct cases.
3. **What kind of principal exists?** Anonymous, HTTP Basic user, JWT authentication, remember-me, or another mechanism.
4. **What are the actual authorities?** `hasRole("READER")` requires `ROLE_READER` under the default prefix; `hasAuthority("report:read")` requires the exact string.
5. **Which component chose the response?** Basic failure handler, exception translation entry point, denied handler, CSRF handler, or generic WebFlux error handler.
6. **Are status/headers/body consistent?** With Basic/Bearer, `WWW-Authenticate` can be part of the API contract.
7. **Is the response already committed?** For streaming, protect before sending data.

You can raise logging appropriately in development, e.g., temporary configuration:

```properties
logging.level.org.springframework.security=DEBUG
```

Do not leave sensitive logging enabled indefinitely in production and never log raw `Authorization` headers, passwords, session cookies, or full JWTs. If tracing is needed, use controlled request/correlation IDs and generic error codes.

### Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| No credentials yet getting 403 | Custom policy/entry point, unexpected principal context, or authentication chain | Check anonymous/trust resolver, chain, and entry point |
| Logged in yet getting 401 | Authentication failed/expired, security context lost in pipeline, or custom entry point | Check credentials, reactive context, and authentication setup |
| Wrong Basic password returns 401 without custom JSON | Error handled by the authentication failure handler | Check `AuthenticationWebFilter` and Basic failure handling separately |
| Correct role yet getting 403 | `ROLE_` prefix confusion; user authorities differ from rule | Safely inspect authorities and compare `hasRole` vs. `hasAuthority` |
| POST returns 403 despite sufficient role | CSRF or HTTP method rule | Identify the 403 source and check CSRF configuration |
| Customized `@ControllerAdvice` yet 401 still uses Spring Security | Error occurred in security filters before the controller | Configure `exceptionHandling`, entry point/auth failure handler |
| Handling error with `block()` hangs requests | Blocking on the reactive event loop | Return `Mono<Void>`, use `writeWith` |
| Streaming response cannot change to 403 | Headers/body already committed before permission denial | Check permissions before streaming |
| Unexpected business error still shows 500 | `ExceptionTranslationWebFilter` is not a generic error handler | Use proper application error handling; do not wrap every exception as `AccessDeniedException` |
| Bearer API returns Basic challenge | Wrong authentication entry point configured for the chain | Configure an appropriate Bearer entry point/headers |
| Unsure whether filter runs before/after authorization | Custom filter inserted at wrong order | Check `SecurityWebFiltersOrder.EXCEPTION_TRANSLATION` and `AUTHORIZATION` |

## 11. Self-Check Exercises

**Question 1.** A user sends no Basic credentials and calls an endpoint requiring `ROLE_READER`. Must an "access denied" decision always become 403?  
**Answer:** No. When valid authentication is missing, `ExceptionTranslationWebFilter` can invoke `ServerAuthenticationEntryPoint`; a Basic API typically returns 401.

**Question 2.** User `guest` logs in validly, yet has only `ROLE_GUEST`. When accessing an endpoint needing `ROLE_READER`, which component typically produces the response?  
**Answer:** `ServerAccessDeniedHandler` invoked by the translation filter after authorization emits `AccessDeniedException`; the demo returns 403 and JSON `ACCESS_DENIED`.

**Question 3.** If the Basic password is wrong, can you state that `ExceptionTranslationWebFilter` always produces the 401?  
**Answer:** No. Failed authentication is typically handled by `AuthenticationWebFilter` along with its failure handler. Distinguish this from `AccessDeniedException` coming from downstream authorization.

**Question 4.** Why should you not use `if (authentication.isAuthenticated())` to distinguish 401/403 in hand-written code?  
**Answer:** Because anonymous authentication can carry `isAuthenticated() == true`. Spring Security uses dedicated trust logic to distinguish anonymous/unauthenticated from authenticated principals.

**Question 5.** If a controller emits `Mono.error(new IllegalStateException("oops"))`, does `ExceptionTranslationWebFilter` automatically convert it to 403?  
**Answer:** No. The translation branch focuses on `AccessDeniedException`; normal application errors are handled by WebFlux/Spring Boot error handling.

**Question 6.** To make every API return the same JSON when authentication is missing, is customizing `exceptionHandling().authenticationEntryPoint(...)` alone sufficient?  
**Answer:** Not necessarily. You must also check authentication failure handlers for Basic, Bearer, form login, and any related security chains; configure properly for your API stack and test each case.

**Question 7.** A `Flux` already sent 10 records to the client and only then emitted `AccessDeniedException`. Can the data be considered protected by exception translation?  
**Answer:** No. Sent information cannot be unsent; a committed response cannot change status/body. Permissions must be checked before streaming data.

## 12. Takeaways and References

- `ExceptionTranslationWebFilter` is the **bridge from downstream access-denied errors to HTTP behavior** in Spring WebFlux.
- It handles `AccessDeniedException` via Reactor `onErrorResume` and picks **`ServerAuthenticationEntryPoint`** or **`ServerAccessDeniedHandler`** using trusted authentication state.
- **401** typically requests authentication; **403** typically means valid authentication with insufficient permissions. Actual statuses also depend on Basic, Bearer, form login, and handler configuration.
- **Wrong Basic passwords** typically belong to `AuthenticationWebFilter` failure handling and should not be assumed to pass through exception translation's JSON.
- In WebFlux use `SecurityWebFilterChain`/`ServerHttpSecurity`, not Servlet's `ExceptionTranslationFilter`.
- Security design must check permissions **before** streaming data, test both happy paths and failure paths, and keep status/headers/body consistent.

**Official Documentation:**

- Spring Security, WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security, `ServerHttpSecurity.exceptionHandling` and `ExceptionHandlingSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security, `AuthenticationWebFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security, `SecurityWebFiltersOrder`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html
- Spring Security, WebFlux authentication testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security, `ExceptionTranslationWebFilter` implementation: https://github.com/spring-projects/spring-security/blob/main/web/src/main/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.java
