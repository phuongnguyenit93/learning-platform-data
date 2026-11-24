# ServerAuthenticationSuccessHandler and ServerAuthenticationFailureHandler

> **Topic:** Spring Security – reactive  
> **Group:** Reactive authentication  
> **Learning objective:** Understand the two callbacks that handle **the outcome of an authentication attempt** inside `AuthenticationWebFilter`, how to continue or complete the HTTP exchange, how to customize them with WebFlux configuration, and how to test with real credentials. All examples below target **Spring WebFlux**, not Spring MVC/Servlet.

## 1. Objectives

After this lesson, you will be able to:

1. Distinguish *authentication* (identity verification) from *authorization* (permission checks), and thus know when success/failure handlers are invoked.
2. Read the signatures of `ServerAuthenticationSuccessHandler` and `ServerAuthenticationFailureHandler` accurately, especially the `Mono<Void>` return type and `WebFilterExchange`.
3. Describe the flow `ServerAuthenticationConverter` → `ReactiveAuthenticationManager` → success/failure handler inside `AuthenticationWebFilter`.
4. Explain why **a successful login does not mean permission to access a resource**, and why a request sending no credentials does not necessarily trigger the failure handler.
5. Configure handlers for HTTP Basic via `ServerHttpSecurity.httpBasic(...)` in Spring Security 6.5; understand how to apply the same pattern to form login and custom filters.
6. Write handlers without `block()`, without manual `subscribe()`, and without leaking passwords, tokens, or exception details.
7. Run a Java 17+ WebFlux application and tests verifying success, failure, 401, 403, and filter-chain continuation.

## 2. Distinguishing Four Security Outcomes

Suppose an API has accounts `reader` (role `READER`) and `admin` (role `ADMIN`). The `/api/admin` endpoint requires `ROLE_ADMIN`. When sending a request, there are at least four distinct situations:

| Case | Was authentication **attempted**? | Authentication outcome | Subsequent behavior |
| --- | --- | --- | --- |
| No HTTP Basic header | Converter usually returns `Mono.empty()`, not attempted | No success/failure result from a Basic attempt | Request continues; if the endpoint requires login, authorization/entry point may return **401** |
| Basic header with wrong username/password | Yes | `AuthenticationException` | **`ServerAuthenticationFailureHandler`** handles it; for Basic APIs typically **401** |
| Valid Basic header, calling an allowed resource | Yes | Authenticated `Authentication` | **`ServerAuthenticationSuccessHandler`** runs; if it continues the chain, controller may return **200** |
| Valid Basic header, yet user lacks `ADMIN` role | Yes | Authentication **succeeded** | Success handler was already invoked; at the later authorization step, access is denied, typically **403** |

**Principle:** `ServerAuthenticationSuccessHandler` is **not** "a handler that returns 200 whenever access is allowed". It reacts to authentication outcomes. `ServerAuthenticationFailureHandler` is **not** "a handler that returns 403 whenever permissions are missing". Authorization errors are handled on a separate path, typically via `ExceptionTranslationWebFilter` and `ServerAccessDeniedHandler`.

```text
HTTP request
  |
  v
AuthenticationWebFilter
  |
  +--> Does URL/method match for authentication?
  |       |
  |       +-- No --> continue WebFilter chain
  |       |
  |       v
  |    ServerAuthenticationConverter
  |       |
  |       +-- Mono.empty() --> do not attempt authentication; continue chain
  |       |
  |       v
  |    ReactiveAuthenticationManager
  |       |
  |       +-- Authentication failed (AuthenticationException)
  |       |       |
  |       |       v
  |       |  ServerAuthenticationFailureHandler
  |       |       |
  |       |       +--> Basic: usually 401/challenge
  |       |       +--> Form: may redirect /login?error
  |       |
  |       +-- Authentication succeeded (Authentication)
  |               |
  |               v
  |          SecurityContext / Reactor Context
  |               |
  |               v
  |          ServerAuthenticationSuccessHandler
  |               |
  |               +--> continue chain --> authorization --> controller
  |               +--> or proactively complete response/redirect
  |
  v
AuthorizationWebFilter (when chain continues)
  |
  +--> sufficient permissions --> business logic
  +--> insufficient permissions --> AccessDeniedException
                          |
                          v
                 ExceptionTranslationWebFilter
                 (entry point / access-denied handler)
```

The diagram omits unrelated filters such as CSRF, headers, and request cache. Actual positions in the security chain depend on the mechanism and configuration. What matters is that **handlers belong to the authentication step**, whereas role/permission checking is a subsequent decision.

## 3. The Two Interfaces and Reactive Contracts

### 3.1. `ServerAuthenticationSuccessHandler`

The Spring Security WebFlux interface is in package `org.springframework.security.web.server.authentication`:

```java
// Illustrative API signature; not a standalone Java file.
Mono<Void> onAuthenticationSuccess(
    WebFilterExchange webFilterExchange,
    Authentication authentication);
```

Arguments:

- `WebFilterExchange`: a wrapper combining `ServerWebExchange` (HTTP request/response) and `WebFilterChain` (the WebFilter chain to continue when appropriate).
- `Authentication`: the **verified** result from the manager, from which `getName()`, principal, and authorities can be read. Do not assume `getCredentials()` is always present or should be logged.
- `Mono<Void>`: asynchronous completion signal; the handler may continue the chain, redirect, or write a response and complete.

Two valid success implementation styles with **different meanings**:

**A. Continue filtering and business processing** (usually right for HTTP Basic/bearer APIs):

```java
ServerAuthenticationSuccessHandler success =
    (webFilterExchange, authentication) ->
        webFilterExchange.getChain()
            .filter(webFilterExchange.getExchange());
```

This is a variable definition inside a configuration with required imports. It is equivalent in intent to `WebFilterChainServerAuthenticationSuccessHandler`: succeed and let downstream filters check permissions and the controller execute. An API can still return 403 **after** the success callback runs if the principal lacks permissions.

**B. Terminate the response at the authentication step** (for example, a dedicated login endpoint):

```java
ServerAuthenticationSuccessHandler success =
    (webFilterExchange, authentication) -> {
        ServerHttpResponse response =
            webFilterExchange.getExchange().getResponse();
        response.setStatusCode(HttpStatus.NO_CONTENT);
        return response.setComplete();
    };
```

This is also only an illustrative snippet inside configuration. It sends 204 and **does not call** the downstream filter chain. **Do not apply style B to all HTTP Basic requests on a resource API** if you still want controllers to handle requests; doing so stops the response right inside the success handler.

### 3.2. `ServerAuthenticationFailureHandler`

Same package, signature:

```java
// Illustrative API signature; not a standalone Java file.
Mono<Void> onAuthenticationFailure(
    WebFilterExchange webFilterExchange,
    AuthenticationException exception);
```

- `AuthenticationException` describes a failed authentication attempt; typically bad credentials, invalid account state, or identity provider rejection.
- The failure handler **has no authenticated `Authentication` argument**. Never fabricate a trusted principal from client data in the failure branch.
- With HTTP Basic, it usually returns 401 and header `WWW-Authenticate: Basic ...`. With form login, it usually redirects to the login page with an error indicator.
- Do not return distinct details like "user does not exist" vs "wrong password" to the client if that allows account enumeration; never put raw exceptions, passwords, or access tokens into responses.

Example of a very short failure handler:

```java
ServerAuthenticationFailureHandler failure =
    (webFilterExchange, exception) -> {
        ServerHttpResponse response =
            webFilterExchange.getExchange().getResponse();
        response.setStatusCode(HttpStatus.UNAUTHORIZED);
        return response.setComplete();
    };
```

This snippet does **not** set `WWW-Authenticate` yet. In real HTTP Basic usage, return an appropriate challenge; the runnable example below includes this header.

### 3.3. Why Is `WebFilterExchange` Needed Instead of Just `ServerWebExchange`?

`ServerWebExchange` gives you the exchange's request, response, attributes, and principal. `WebFilterExchange` **also wraps `WebFilterChain`**. The filter chain is required so the success handler has the option to "let the request proceed":

```java
WebFilterChain chain = webFilterExchange.getChain();
ServerWebExchange exchange = webFilterExchange.getExchange();
return chain.filter(exchange);
```

This is an illustrative snippet placed inside a handler method with `WebFilterChain` and `ServerWebExchange` imports. Both `getChain()` and `getExchange()` are APIs on `WebFilterExchange`. Do not look for `getChain()` directly on `ServerWebExchange`.

## 4. How Does `AuthenticationWebFilter` Invoke the Handlers?

In WebFlux, `AuthenticationWebFilter` belongs to `org.springframework.security.web.server.authentication`. You can use it indirectly via `ServerHttpSecurity.httpBasic(...)`/`formLogin(...)` or directly for a custom authentication mechanism.

Overall flow:

1. **Matcher:** `setRequiresAuthenticationMatcher(...)` determines which requests trigger an authentication attempt. If it does not match, the filter continues the chain without calling success/failure handlers.
2. **Converter:** `ServerAuthenticationConverter` turns `ServerWebExchange` into an unauthenticated `Mono<Authentication>`. HTTP Basic uses `ServerHttpBasicAuthenticationConverter` to extract username/password from `Authorization`. If the converter emits `Mono.empty()`, there is no authentication attempt to yield success or failure.
3. **Authentication manager:** `ReactiveAuthenticationManager.authenticate(authentication)` verifies the evidence and reactively returns an authenticated result or an error signal.
4. **Success outcome:** Spring Security builds/saves `SecurityContext` via the configured `ServerSecurityContextRepository`, places the authentication into the reactive context for the downstream branch, and invokes the success handler.
5. **Failure outcome:** the `AuthenticationException` branch is routed to the corresponding failure handler, unless transformed into another error type.
6. **Downstream:** runs only if the appropriate handler continues the chain. When downstream requires additional permissions, authorization can still return 403.

Never confuse `AuthenticationException` with `AccessDeniedException`:

| Concept | Signal | Step that typically handles it |
| --- | --- | --- |
| Authentication rejected | `AuthenticationException` | Failure handler of the authentication filter or authentication mechanism |
| Authorization rejected after authentication | `AccessDeniedException` | Exception translation and access-denied handler |
| Unauthenticated call to a protected endpoint | Usually authorization denial due to missing identity | Authentication entry point to request credentials |
| Business logic throws another error, e.g. `IllegalStateException` | Application exception | WebFlux application error handling, not automatically a security failure |

**Important case:** A user who sends no HTTP Basic header yet hits a protected endpoint may receive 401 **without a custom `ServerAuthenticationFailureHandler` running**. Because the converter returned empty, there was no failed authentication attempt; the authorization/entry point step is what requests authentication.

### 4.1. Default Behavior by Mechanism

| Mechanism | Typical success | Typical failure |
| --- | --- | --- |
| HTTP Basic | `WebFilterChainServerAuthenticationSuccessHandler`: continues chain | `ServerAuthenticationEntryPointFailureHandler`: delegates to entry point producing HTTP Basic challenge/401 |
| Form login | `RedirectServerAuthenticationSuccessHandler`: redirects to saved request URL or default page | `RedirectServerAuthenticationFailureHandler`: redirects to login page with error flag |
| Custom `AuthenticationWebFilter` | Default success continues chain | Default failure prompts for Basic authentication; explicitly configure for custom mechanisms |
| OAuth2/JWT | Depends on component/mechanism; may be redirect handler or bearer failure/entry point | Depends on flow and mechanism; do not assume Basic handler applies to tokens |

Spring Security's defaults can be changed via configuration. When working with a real system, inspect the **selected filter and security chain**, along with the active authentication mechanism.

### 4.2. `ServerSecurityContextRepository` Is a Separate Concern

The success handler decides how to respond or continue the request. `ServerSecurityContextRepository` decides **how to save and load SecurityContext**, for instance via session or statelessly. A success handler sending 200/204 **does not automatically issue a JWT, create a long-lived session, or grant a refresh token**. HTTP Basic sends credentials on every request; session persistence for form login has its own mechanism. Configure the context repository according to your design rather than making `authenticationSuccessHandler` shoulder the whole identity/session system.

## 5. Runnable Java 17+ Example: Customizing HTTP Basic Success/Failure

The example pins **Spring Boot 3.5.16** for reproducibility during study, corresponding to Spring Security 6.5.x via dependency management. This is a historical branch past OSS end-of-support; for real production deployments, pick a supported Spring Boot line and check API compatibility. The goal here is learning how handlers are called, so the source pre-populates demo users and uses GET only.

**Rules of the example:**

- No credentials, `GET /api/public` → 200, triggers neither success nor failure.
- User `reader` with correct password calling `/api/private` → success handler adds `X-Auth-Result: SUCCESS` header and continues chain → controller returns 200.
- Wrong password → failure handler returns 401, HTTP Basic challenge header, JSON `AUTHENTICATION_FAILED`.
- Authenticated `reader` calling `/api/admin` → success handler already ran, yet authorization lacks `ROLE_ADMIN` → 403.
- `admin` with correct password calling `/api/admin` → 200.

The `X-Auth-Result` header is strictly an **observation marker for this lesson**, not a mechanism proving identity to clients or a method of granting permissions. Production should use controlled metrics/logs instead of exposing unnecessary internal state.

### 5.1. File Structure

```text
reactive-auth-handlers/
├── pom.xml
└── src/
    ├── main/java/demo/handlers/
    │   ├── Application.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/demo/handlers/
        └── AuthenticationHandlersTests.java
```

### 5.2. `pom.xml`

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
    <artifactId>reactive-auth-handlers</artifactId>
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

`starter-webflux` provides WebFlux and Reactor; `starter-security` provides security; `starter-test` and `spring-security-test` participate only during tests. Do not pin a separate Spring Security version when using the Boot BOM.

### 5.3. `src/main/java/demo/handlers/Application.java`

```java
package demo.handlers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 5.4. `src/main/java/demo/handlers/SecurityConfiguration.java`

```java
package demo.handlers;

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
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        ServerAuthenticationSuccessHandler success =
            (webFilterExchange, authentication) -> {
                // Observation marker strictly for this lesson.
                webFilterExchange.getExchange()
                    .getResponse()
                    .getHeaders()
                    .set("X-Auth-Result", "SUCCESS");

                // Keep request pipeline intact: authorization still runs afterwards.
                return webFilterExchange.getChain()
                    .filter(webFilterExchange.getExchange());
            };

        ServerAuthenticationFailureHandler failure =
            (webFilterExchange, exception) -> {
                ServerHttpResponse response =
                    webFilterExchange.getExchange().getResponse();

                response.setStatusCode(HttpStatus.UNAUTHORIZED);
                response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
                response.getHeaders().set(
                    HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"reactive-demo\"");

                // Never return exception.getMessage(), username, or password.
                byte[] bytes = "{\"code\":\"AUTHENTICATION_FAILED\"}"
                    .getBytes(StandardCharsets.UTF_8);

                return response.writeWith(Mono.just(
                    response.bufferFactory().wrap(bytes)));
            };

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/private", "/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic
                .authenticationSuccessHandler(success)
                .authenticationFailureHandler(failure)
            )
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
```

**Reading the code by handler meaning:**

- `httpBasic(...)` configures the HTTP Basic authentication filter; in Spring Security 6.5, `HttpBasicSpec` has setters `authenticationSuccessHandler` and `authenticationFailureHandler`.
- The success handler **does not hard-set** status 200, nor does it call `setComplete()`. It writes an observation header and then calls `webFilterExchange.getChain().filter(...)`. That is what lets `AuthorizationWebFilter` and the controller execute downstream.
- The failure handler receives `AuthenticationException` and writes **401** plus a JSON body. For HTTP Basic, `WWW-Authenticate: Basic realm="reactive-demo"` signals the proper challenge type.
- `formLogin(...disable())` avoids default form login/redirect behavior so the lesson stays focused on Basic.
- `roles("ADMIN")` creates the `ROLE_ADMIN` authority. `hasRole("ADMIN")` checks that authority using the default prefix; it does not authenticate users on its own.
- `MapReactiveUserDetailsService` stores accounts in memory. `{noop}` **does not hash passwords** and is valid only as a demo; production must use strong password hashing, secret management, and HTTPS.
- All demo endpoints are GET. Never disable CSRF indiscriminately; if switching to form login and state-changing requests, appropriate CSRF tokens/strategies are required.

**Limitation of custom callbacks:** A simple custom failure handler converting every `AuthenticationException` into 401 can mask infrastructure errors such as a failing identity provider/database. Production must distinguish `AuthenticationServiceException` from bad credentials and choose dedicated logging/handling per policy. `ServerAuthenticationEntryPointFailureHandler` has behavior that can rethrow `AuthenticationServiceException` by default; when replacing it with a custom handler, verify that behavior.

### 5.5. `src/main/java/demo/handlers/DemoController.java`

```java
package demo.handlers;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public OK");
    }

    @GetMapping("/private")
    public Mono<String> privateInfo() {
        return Mono.just("private OK");
    }

    @GetMapping("/admin")
    public Mono<String> adminInfo() {
        return Mono.just("admin OK");
    }

    @GetMapping("/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
```

`/api/me` shows that authentication has been placed into the Reactor security context and can be read by downstream handlers. `ReactiveSecurityContextHolder` is the reactive mechanism, different from using Servlet-style `ThreadLocal` to access principal info.

## 6. Testing with `WebTestClient`: Must Use Real Credentials

If you only use `mockUser()` or `@WithMockUser`, tests pre-populate an authenticated principal and can skip the real credential processing path, so they **do not prove that success/failure callbacks inside `AuthenticationWebFilter` ran**. To test this lesson, the relevant requests must actually send `Authorization: Basic ...`.

Use `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` to test the entire WebFlux security chain inside the test suite without opening a TCP port.

### 6.1. `src/test/java/demo/handlers/AuthenticationHandlersTests.java`

```java
package demo.handlers;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class AuthenticationHandlersTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicRequestDoesNotRequireAuthenticationAttempt() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist("X-Auth-Result")
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void missingBasicHeaderUsesAuthenticationEntryPoint() {
        client.get().uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE)
            .expectHeader().doesNotExist("X-Auth-Result");
    }

    @Test
    void invalidPasswordInvokesFailureHandler() {
        client.get().uri("/api/private")
            .headers(headers -> headers.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"reactive-demo\"")
            .expectHeader().contentTypeCompatibleWith(
                org.springframework.http.MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.code").isEqualTo("AUTHENTICATION_FAILED");
    }

    @Test
    void unknownUsernameInvokesFailureHandler() {
        client.get().uri("/api/private")
            .headers(headers -> headers.setBasicAuth("unknown", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody()
            .jsonPath("$.code").isEqualTo("AUTHENTICATION_FAILED");
    }

    @Test
    void successHandlerContinuesToController() {
        client.get().uri("/api/private")
            .headers(headers -> headers.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Auth-Result", "SUCCESS")
            .expectBody(String.class).isEqualTo("private OK");
    }

    @Test
    void successfulAuthenticationCanStillBeForbidden() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().valueEquals("X-Auth-Result", "SUCCESS");
    }

    @Test
    void adminWithCorrectCredentialsMayAccessAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Auth-Result", "SUCCESS")
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void authenticatedPrincipalIsAvailableDownstream() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Auth-Result", "SUCCESS")
            .expectBody(String.class).isEqualTo("reader");
    }

    @Test
    void invalidCredentialsOnPublicRouteStillFailAuthentication() {
        client.get().uri("/api/public")
            .headers(headers -> headers.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody()
            .jsonPath("$.code").isEqualTo("AUTHENTICATION_FAILED");
    }
}
```

**Why is the last test noteworthy?** The `permitAll()` rule means the endpoint does not require authentication to be accessed; it does **not** mean Spring Security is forced to ignore any credentials sent by the client. The Basic filter can still attempt to verify the supplied header and emit a failure before the request reaches authorization.

### 6.2. Result Matrix

| Request | Success handler | Failure handler | Expected status | Explanation |
| --- | --- | --- | --- | --- |
| `GET /api/public`, no header | No | No | **200** | Public, converter creates no authentication attempt |
| `GET /api/private`, no header | No | No | **401** | Authentication entry point demands valid evidence |
| `GET /api/private`, `reader:wrong` | No | **Yes** | **401** + JSON code | Invalid credentials |
| `GET /api/private`, `unknown:wrong` | No | **Yes** | **401** + JSON code | Nonexistent user, without leaking details to client |
| `GET /api/private`, `reader:reader123` | **Yes** | No | **200** + success header | Authentication succeeded, controller runs |
| `GET /api/admin`, `reader:reader123` | **Yes** | No | **403** | Authentication valid, authorization lacks `ROLE_ADMIN` |
| `GET /api/admin`, `admin:admin123` | **Yes** | No | **200** | Has `ROLE_ADMIN` permission |
| `GET /api/me`, `reader:reader123` | **Yes** | No | **200**, body `reader` | Reactive context lets handler read principal |
| `GET /api/public`, `reader:wrong` | No | **Yes** | **401** | Public requests can still fail when client actively sends wrong credentials |

An `AuthenticationException` raised because an external authentication system lost connectivity should not necessarily be mapped to a wrong-password error. The test suite above only tests in-memory username/password; production should add tests for infrastructure failures, rate limits, and appropriate timeouts.

## 7. Running and Observing in the Terminal

In the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

JDK 17+ and compatible Maven must be present. With the listed code, **9 `@Test` methods** are expected to run. Inspect Maven Surefire reports under `target/surefire-reports`. Exact build messages and test timings vary per machine; verify actual status from your run output.

Launch:

```bash
mvn spring-boot:run
```

Call with `curl` in another terminal:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/private
curl -i -u reader:wrong http://localhost:8080/api/private
curl -i -u reader:reader123 http://localhost:8080/api/private
curl -i -u reader:reader123 http://localhost:8080/api/admin
curl -i -u admin:admin123 http://localhost:8080/api/admin
curl -i -u reader:reader123 http://localhost:8080/api/me
```

In Windows PowerShell, pick `curl.exe` if `curl` is aliased to a cmdlet. The commands above use demo users and localhost HTTP; never carry sample passwords into real environments.

With a wrong password, sample response:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Basic realm="reactive-demo"

{"code":"AUTHENTICATION_FAILED"}
```

With valid `reader` calling `/api/private`:

```http
HTTP/1.1 200 OK
X-Auth-Result: SUCCESS
Content-Type: text/plain;charset=UTF-8

private OK
```

With valid `reader` calling `/api/admin`:

```http
HTTP/1.1 403 Forbidden
X-Auth-Result: SUCCESS
```

Meaning of the last output: the `X-Auth-Result: SUCCESS` header only confirms the **authentication step** succeeded; the response is still 403 because the **permission check** rejected it. HTTP headers such as `Content-Length`, `Date`, or the 403 error body vary by server/configuration and are not fixed in this example.

## 8. When to Use Built-in Handlers Instead of Lambdas?

Spring Security already provides several implementations:

| Implementation | Job |
| --- | --- |
| `WebFilterChainServerAuthenticationSuccessHandler` | After authentication success, continues `WebFilterChain`. Fits Basic API style |
| `RedirectServerAuthenticationSuccessHandler` | Redirects after login, optionally considering saved request and default URL; common in form login |
| `RedirectServerAuthenticationFailureHandler` | Redirects to a login error URL |
| `ServerAuthenticationEntryPointFailureHandler` | Adapts an entry point into a failure handler, often used to return a challenge on auth failure |
| `DelegatingServerAuthenticationSuccessHandler` | Coordinates multiple success handlers per a specific design |
| `ConcurrentSessionControlServerAuthenticationSuccessHandler` | Supports concurrent session control when session policies/registries are configured |

Do not replace HTTP Basic's default success handler with a redirect handler or `setComplete` casually; Basic authentication runs on resource requests, and controllers usually need to continue handling the request. Conversely, a form login endpoint can **intentionally end the response** with a redirect or 204.

### 8.1. Form Login Configuration (Supplemental Snippet)

The snippet below **does not belong to the Basic project in section 5**; use it when you have a WebFlux form-based login application where login requests are typically `POST /login`. Place it inside `ServerHttpSecurity` configuration:

```java
.formLogin(form -> form
    .authenticationSuccessHandler(
        new RedirectServerAuthenticationSuccessHandler("/dashboard"))
    .authenticationFailureHandler(
        new RedirectServerAuthenticationFailureHandler("/login?error")))
```

You need to import `RedirectServerAuthenticationSuccessHandler` and `RedirectServerAuthenticationFailureHandler` from package `org.springframework.security.web.server.authentication`.

Form login by default processes username/password from form data and is usually paired with sessions. For browser applications, protect against CSRF when needed and handle cookies/sessions, session fixation, session limits, and logout. Never assume form login shares the same policy from the stateless Basic model, and never assume changing only handlers constitutes a complete login design.

### 8.2. Custom `AuthenticationWebFilter`: Where Handlers Plug In

When building a custom authentication flow, you can assemble an `AuthenticationWebFilter` with a `ReactiveAuthenticationManager` and configure:

```java
// Illustrative skeleton; not a standalone program.
AuthenticationWebFilter filter = new AuthenticationWebFilter(manager);
filter.setRequiresAuthenticationMatcher(matcher);
filter.setServerAuthenticationConverter(converter);
filter.setAuthenticationSuccessHandler(successHandler);
filter.setAuthenticationFailureHandler(failureHandler);
filter.setSecurityContextRepository(repository);
```

Here `manager`, `matcher`, `converter`, `repository`, and handlers are components **the application must supply**, not pre-defined Java variables. You must register the filter into the security chain at the proper position and verify filter order. Specifically, if the converter returns `Mono.empty()`, there is no authentication attempt for a success/failure handler to process.

In multi-mechanism flows (Basic, bearer, form, mTLS...), each authentication filter can have its own handlers. Do not let a Basic handler set "catch all authentication errors" if the request is actually handled by an OAuth2/Bearer filter.

## 9. Using `Mono<Void>` Correctly in Handlers

### 9.1. Do Not Use `block()` or Call `subscribe()` Manually

A reactive handler must **return a publisher** representing the work to be done. If an audit event must be written asynchronously, the conceptual pattern is:

```java
// Illustrative, depends on an application-provided auditService.
ServerAuthenticationSuccessHandler success = (exchange, auth) ->
    auditService.recordLoginSuccess(auth.getName())
        .then(exchange.getChain().filter(exchange.getExchange()));
```

In this snippet `auditService.recordLoginSuccess(...)` must return `Mono<Void>` (or a compatible publisher). **This is non-standalone illustrative code**; do not use it without defining an audit service and an audit error-handling policy. If auditing must not break login, handle audit errors explicitly and transparently. Never call `auditService.record(...).subscribe()` and return `Mono.empty()`, as that creates a detached subscription, breaks error/cancellation control, and loses context.

### 9.2. Complete Responses Properly After Writing

When writing a body yourself, use `ServerHttpResponse.writeWith(...)` and return `Mono<Void>`. If you only want a status code, `response.setComplete()` is appropriate. Never call `response.setStatusCode(UNAUTHORIZED)` and then continue the filter chain after deciding to reject; downstream can write extra data or hit a committed response that cannot be altered.

Similarly, never both `response.writeWith(...)` and `chain.filter(...)` afterwards without clear reason and control: that can write the response twice or muddy the meaning of authentication failure.

### 9.3. Which Data Is Safe for Logs/Responses?

- You may record events like "authentication success/failure", request/correlation ID, timestamp, and authentication type at an appropriate level.
- Never log passwords, tokens, `Authorization` header contents, session secrets, `authentication.getCredentials()`, or verbatim exception messages.
- Never distinguish "user exists" from "wrong password" in observable responses. Use a common `AUTHENTICATION_FAILED` code when appropriate.
- Consider timeouts, backpressure, retries, rate limiting, and async audit logging per operational policy; do not turn handlers into event-loop-blocking I/O.
- With OAuth2/OIDC, failure/success redirects or token responses must follow the protocol; never replace them with arbitrary JSON that breaks state/nonce/PKCE or the active flow.

## 10. Debugging: Distinguishing Callbacks from Exception Translation and Authorization

Looking solely at a 401 or 403 response is **not enough to conclude** which callback ran. Trace in order:

1. Did the request match the `SecurityWebFilterChain` and the authentication filter under inspection?
2. Did the converter produce an `Authentication` or return `Mono.empty()`?
3. Did the manager authenticate successfully, reject, or hit an infrastructure error?
4. Which success/failure handlers are configured on that authentication filter?
5. If the success handler continued the chain, which authority did `AuthorizationWebFilter` require?
6. If authorization emitted `AccessDeniedException`, did `ExceptionTranslationWebFilter` invoke the entry point or denied handler?
7. Did CSRF/CORS filters, multiple security chains, an already-committed response, or an application-level handler intervene?

| Symptom | Usually accurate interpretation | What to check |
| --- | --- | --- |
| Missing Basic header → 401 yet custom failure JSON does not appear | No authentication attempt; entry point asks for login | `ServerAuthenticationConverter`, `ServerAuthenticationEntryPoint` |
| Wrong Basic password → JSON failure 401 | `AuthenticationWebFilter` called failure handler | Password encoder, user store, failure handler |
| Valid Basic yet 403 | Authentication succeeded, authorization failed | `ROLE_`, authorities, policy, and denied handler |
| Valid Basic yet controller never runs | Success handler called `setComplete`/redirect instead of continuing chain | `WebFilterChainServerAuthenticationSuccessHandler` or `getChain().filter` |
| `mockUser` tests pass yet JSON failure is untested | Mock test bypasses credential-based authentication | Use real HTTP Basic or real authentication flow in `WebTestClient` |
| One endpoint redirects to login, another returns 401 | Possibly using form login or different chain/entry point | `formLogin`, `httpBasic`, request matchers, and Accept header |
| Missing permissions yet custom failure handler never runs | `AccessDeniedException` belongs to authorization | `ExceptionTranslationWebFilter`, `ServerAccessDeniedHandler` |
| POST gets 403 despite valid user | Possibly CSRF, not wrong password | CSRF config/token, HTTP method, cookie/session |
| Success handler writes `200` for every request and returns `setComplete` | Controller and downstream rules never run | Redesign success handler for the authentication type |
| Getting 401 instead of identity provider service error | Custom handler turns every `AuthenticationException` into BAD_CREDENTIALS | Distinguish `AuthenticationServiceException`, metrics, and error policy |
| Identity lost after async operations | Detached subscription or reading ThreadLocal outside Reactor | `ReactiveSecurityContextHolder`, Reactor pipeline |
| Error body contains raw exception/token | Sensitive data leakage | Use generic error codes, strip secret details |

## 11. Self-Check Questions

**Question 1.** A user sends valid HTTP Basic username/password and calls an endpoint requiring a role the user lacks. Will the success or failure handler run? What can the final HTTP status be?

**Answer:** Authentication succeeded, so **the success handler runs**. If success continues the chain, the subsequent authorization step can reject and return **403**. Do not invoke authentication failure merely for missing permissions.

**Question 2.** With no HTTP Basic header, calling an endpoint requiring login returns 401. Did `ServerAuthenticationFailureHandler` definitely run?

**Answer:** No. The converter can return `Mono.empty()`, the filter skips the authentication attempt, and then the entry point on the authorization path produces 401.

**Question 3.** Why must Basic's success handler usually continue the chain?

**Answer:** Basic credentials are attached to the current resource request. Once authenticated, the request still needs to pass through authorization and the handler/controller; calling `setComplete()` early halts all further processing.

**Question 4.** Does `ServerAuthenticationFailureHandler` receive `AuthenticationException` or `AccessDeniedException`?

**Answer:** `AuthenticationException`. `AccessDeniedException` typically belongs to permission checking and exception translation.

**Question 5.** For the same HTTP 401, can missing credentials and wrong credentials go through two different handlers?

**Answer:** Yes. Missing credentials are typically handled by authorization/entry point asking for authentication; wrong credentials are typically handled by the authentication failure handler. Responses can differ if those handlers are customized inconsistently.

**Question 6.** Why is `@WithMockUser` not enough to prove the password failure handler was invoked?

**Answer:** Because `@WithMockUser` sets a fake already-authenticated principal and does not execute real username/password verification through `ReactiveAuthenticationManager`.

**Question 7.** If a custom failure handler calls `response.writeWith(...)` and then calls `chain.filter(exchange)`, what can happen?

**Answer:** The rejected request still flows downstream and may trigger a second response write or unintended data processing; return the publisher completing the response and stop the chain.

**Question 8.** A handler returns `Mono<Void>` yet calls a blocking API with `block()` inside it. Is that appropriate for WebFlux?

**Answer:** No. Returning `Mono<Void>` does not automatically make blocking operations non-blocking. Compose asynchronous publishers with `flatMap`, `then`, `writeWith`, or design proper integration.

**Question 9.** When switching from form login to Bearer JWT, can you reuse `WWW-Authenticate: Basic ...` in the failure handler?

**Answer:** No. Responses must follow the Bearer mechanism and active resource server configuration. Success/failure handlers may belong to a different filter and should not blindly reuse Basic callbacks.

## 12. Takeaways and References

- `ServerAuthenticationSuccessHandler` receives a **valid `Authentication`** and `WebFilterExchange`, returning `Mono<Void>`; it can **continue the chain** or **terminate the response**, depending on the flow.
- `ServerAuthenticationFailureHandler` receives **`AuthenticationException`** and typically produces an HTTP challenge, error response, or redirect, with no authenticated principal.
- **Authentication success ≠ authorization success**. Valid HTTP Basic lacking `ROLE_ADMIN` can still yield 403 downstream.
- **No credentials ≠ failed authentication attempt**. A converter returning empty prevents the failure handler from running; another entry point can return 401.
- For WebFlux, use `ServerHttpSecurity`, `AuthenticationWebFilter`, `WebFilterExchange`, and `ReactiveSecurityContextHolder`; never mix in Servlet interfaces like `AuthenticationSuccessHandler` or `AuthenticationFailureHandler`.
- Write responses reactively, never log credentials, never start manual subscriptions inside handlers, and test status/headers/bodies together with `WebTestClient`.

**Official references:**

- Spring Security 6.5 – `ServerAuthenticationSuccessHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationSuccessHandler.html
- Spring Security 6.5 – `ServerAuthenticationFailureHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationFailureHandler.html
- Spring Security 6.5 – `AuthenticationWebFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security 6.5 – `ServerHttpSecurity.HttpBasicSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security 6.5 – `ServerHttpSecurity.FormLoginSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security – Reactive authentication testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security – WebTestClient security setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
